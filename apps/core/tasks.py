import hmac
import os
import shutil
from abc import ABC, abstractmethod, abstractproperty
from hashlib import sha256

import requests
from celery.app.task import Task as CeleryTask
from celery.signals import task_prerun, task_retry
from celery.utils.log import get_task_logger
from django.apps import apps
from django.conf import settings
from django.db import models, router, transaction
from py_zipkin.zipkin import zipkin_span
from settings.celeryconf import app, register_task

from apps.core import zipkin
from apps.core.backends.storage import default_storage
from apps.core.exceptions import ObjectProcessingError
from apps.core.helpers import Cached, get_tracing_attrs, redis, set_tracing_attrs
from apps.core.middleware import clear_request_data
from apps.core.mixins import TaskLockMixin
from apps.instances.helpers import get_current_instance, set_current_instance
from apps.instances.models import Instance


class BaseTask(CeleryTask):
    logger = None

    @classmethod
    def get_logger(cls):
        if cls.logger is None:
            cls.logger = get_task_logger('celery_tasks')
        return cls.logger

    @staticmethod
    @task_prerun.connect
    def task_prerun_handler(sender, **kwargs):
        clear_request_data()

    def apply_async(self, args=None, kwargs=None, task_id=None, producer=None,
                    link=None, link_error=None, **options):
        kwargs = kwargs or {}
        tracing_dict = zipkin.create_dict_from_zipkin_attrs(get_tracing_attrs())
        if tracing_dict is not None:
            kwargs['tracing'] = tracing_dict
        return super().apply_async(args, kwargs, task_id, producer, link, link_error,
                                   **options)

    def __call__(self, *args, **kwargs):
        zipkin_attrs = zipkin.create_zipkin_attr_from_dict(kwargs.pop('tracing', None))
        set_tracing_attrs(zipkin_attrs)

        if not zipkin_attrs.is_sampled:
            return super().__call__(*args, **kwargs)

        with zipkin_span(
            service_name=settings.TRACING_SERVICE_NAME,
            span_name='{0}.{1}'.format(self.__module__, self.__class__.__name__),
            zipkin_attrs=zipkin_attrs,
            transport_handler=zipkin.transport_handler,
            host='127.0.0.1',
        ):
            return super().__call__(*args, **kwargs)

    @staticmethod
    @task_retry.connect
    def task_retry_handler(sender, request, reason, **kwargs):
        sender.get_logger().warning(
            'Retrying {task_name}[{task_id}] args:{args} kwargs:{kwargs} error:{exc!r}'.format(
                exc=reason, task_name=sender.__name__, task_id=request.id, args=request.args,
                kwargs=request.kwargs,
            )
        )


class InstanceBasedTask(app.Task):
    instance_lookup_param = 'instance_pk'
    instance_attr_name = 'instance'

    def __call__(self, *args, **kwargs):
        logger = self.get_logger()
        instance_pk = kwargs.get(self.instance_lookup_param)

        try:
            instance = Cached(Instance, kwargs=dict(pk=instance_pk)).get()
            setattr(self, self.instance_attr_name, instance)
            set_current_instance(instance)
        except Instance.DoesNotExist:
            setattr(self, self.instance_attr_name, None)
            logger.warning('Instance no longer exists: Instance[pk=%s]', instance_pk)
            return

        return super().__call__(*args, **kwargs)


@register_task
class DeleteLiveObjectTask(app.Task):
    default_retry_delay = 10

    def run(self, model_class_name, object_pk, instance_pk=None, **kwargs):
        logger = self.get_logger()

        try:
            model_class = apps.get_model(model_class_name)
        except (LookupError, ValueError):
            # do not retry
            raise

        if instance_pk is not None:
            try:
                instance = Cached(Instance, kwargs=dict(pk=instance_pk)).get()
                set_current_instance(instance)
            except Instance.DoesNotExist:
                logger.warning(
                    'Error occurred during deletion of %s[pk=%s] in Instance[pk=%s]. '
                    'Instance no longer exists.',
                    model_class_name, object_pk, instance_pk)
                return

            logger.info('Deleting %s[pk=%s] in %s.',
                        model_class_name, object_pk, instance)
        else:
            logger.info('Deleting %s[pk=%s] in public schema.',
                        model_class_name, object_pk)

        try:
            db = router.db_for_write(model_class)
            with transaction.atomic(db):
                model_class.all_objects.filter(pk=object_pk).delete()
        except Exception as exc:
            raise self.retry(exc=exc)


@register_task
class DeleteFilesTask(TaskLockMixin, app.Task):
    buckets = (settings.STORAGE_BUCKET, settings.STORAGE_HOSTING_BUCKET)

    def run(self, prefix, all_buckets=False):
        """
        Remove all files with path starting with given prefix
        """

        storage = default_storage

        if settings.STORAGE_TYPE == 'local':
            path_to_del = os.path.join(default_storage.location, prefix)
            if os.path.exists(path_to_del):
                shutil.rmtree(path_to_del)
            return

        if not prefix.endswith('/'):
            prefix += '/'

        buckets = self.buckets
        if not all_buckets:
            buckets = buckets[:1]

        if settings.STORAGE_TYPE == 's3':
            s3 = storage.connection
            for bucket_name in buckets:
                s3.Bucket(bucket_name).objects.filter(Prefix=prefix).delete()
            return

        if settings.STORAGE_TYPE == 'gcloud':
            gcloud = storage.client
            for bucket_name in buckets:
                bucket = gcloud.get_bucket(bucket_name)
                for blob in bucket.list_blobs(prefix=prefix):
                    bucket.delete(blob)
            return


class ObjectProcessorBaseTask(TaskLockMixin, InstanceBasedTask, ABC):
    default_retry_delay = 10
    max_attempts = 1
    model_class = models.Model

    @abstractproperty
    def query(self):
        return

    @abstractmethod
    def process_object(self, obj, **kwargs):
        return

    def get_task_key(self, *args, **kwargs):
        return '%s:%s' % (self.name, kwargs['instance_pk'])

    def get_attempt_key(self, *args, **kwargs):
        return 'attempt:%s' % self.get_task_key(*args, **kwargs)

    def get_lock_key(self, *args, **kwargs):
        return 'lock:%s' % self.get_task_key(*args, **kwargs)

    def save_object(self, obj):
        # If needed and there was no error - save everything that was changed
        changes = obj.whats_changed()
        if changes:
            changes.add('updated_at')
            obj.save(update_fields=changes)

    def handle_exception(self, obj, exc):
        raise NotImplementedError  # pragma: no cover

    def run(self, **kwargs):
        logger = self.get_logger()
        instance_pk = self.instance.pk
        self.countdown = None

        obj = self.model_class.objects.filter(**self.query).order_by('updated_at').first()
        if not obj:
            return

        # Increase attempt key for an object and check if we haven't exceeded max attempts to process it
        attempt_key = self.get_attempt_key(instance_pk=instance_pk)
        attempt = redis.incr(attempt_key)
        redis.expire(attempt_key, self.lock_expire)

        logger.info('Processing of %s[pk=%s] in Instance[pk=%s]. Attempt #%d.',
                    self.model_class.__name__, obj.pk, instance_pk, attempt)

        try:
            if self.process_object(obj, **kwargs) is not False:
                self.save_object(obj)
        except ObjectProcessingError as exc:
            if attempt < self.max_attempts and exc.retry:
                logger.warning('ProcessingError during processing of %s[pk=%s] in Instance[pk=%s]. Retrying.',
                               self.model_class.__name__, obj.pk, instance_pk, exc_info=1)
                return

            logger.warning('ProcessingError during processing of %s[pk=%s] in Instance[pk=%s].',
                           self.model_class.__name__, obj.pk, instance_pk, exc_info=1)
            self.handle_exception(obj, exc)
        except Exception as exc:
            # Return if encountered unexpected error. We will retry in after lock handler.
            if attempt < self.max_attempts:
                logger.warning('Unhandled error during processing of %s[pk=%s] in Instance[pk=%s]. Retrying.',
                               self.model_class.__name__, obj.pk, instance_pk, exc_info=1)
                self.countdown = attempt * self.default_retry_delay
                return

            # Otherwise if we reached max attempts - log it
            logger.error('Unhandled error during processing of %s[pk=%s] in Instance[pk=%s].',
                         self.model_class.__name__, obj.pk, instance_pk, exc_info=1)
            self.handle_exception(obj, exc)

        # No unexpected error encountered - we're done, reset attempts
        redis.delete(attempt_key)

    def after_lock_released(self, args, kwargs):
        if get_current_instance() and self.model_class.objects.filter(**self.query).exists():
            options = {}
            if self.countdown is not None:
                options['countdown'] = self.countdown
            self.apply_async(args, kwargs, **options)


@register_task
class SyncInvalidationTask(app.Task):
    default_retry_delay = 10

    def run(self, version_key, **kwargs):
        signature = hmac.new('{}:{}'.format(version_key, settings.SECRET_KEY).encode(),
                             digestmod=sha256).hexdigest()
        for loc in settings.LOCATIONS:
            if loc == settings.LOCATION:
                continue

            url = 'https://{url}/v3/cache_invalidate/'.format(url=settings.API_LOCATION_DOMAIN.format(location=loc))
            requests.post(url, data={'version_key': version_key, 'signature': signature}).raise_for_status()
