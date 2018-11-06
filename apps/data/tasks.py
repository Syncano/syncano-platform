from collections import defaultdict

from django.conf import settings
from django.db import connections, transaction
from settings.celeryconf import register_task

from apps.core.mixins import TaskLockMixin
from apps.core.tasks import InstanceBasedTask, ObjectProcessorBaseTask
from apps.data.helpers import DROP_INDEX_SQL, SELECT_INDEX_SQL, process_data_object_index
from apps.instances.helpers import get_instance_db

from .models import Klass

INDEX_LOCK_KEY_TEMPLATE = 'lock:index:{instance_pk}'


@register_task
class IndexKlassTask(ObjectProcessorBaseTask):
    lock_blocking_timeout = None
    default_retry_delay = settings.DATA_OBJECT_INDEXING_RETRY
    model_class = Klass
    query = {'index_changes__isnull': False}

    def get_lock_key(self, *args, **kwargs):
        return INDEX_LOCK_KEY_TEMPLATE.format(instance_pk=kwargs['instance_pk'])

    @classmethod
    def process_indexes(cls, instance, klass_pk, index_changes, concurrently, record_done=None):
        for index_type, index_op in index_changes.items():
            for index_op_type, index_list in index_op.items():
                create = index_op_type == '+'

                for index_data in index_list:
                    process_data_object_index(instance=instance,
                                              klass_pk=klass_pk,
                                              index_type=index_type,
                                              index_data=index_data,
                                              concurrently=concurrently,
                                              create=create)
                    if record_done is not None and create:
                        record_done[index_type].append(index_data[0])

    def handle_exception(self, obj, exc):
        # Unlock klass nonetheless, but cleanup indexes
        obj.unlock(self.index_changes_done, rollback=True)

    def process_object(self, obj, **kwargs):
        self.index_changes_done = defaultdict(list)
        self.process_indexes(instance=self.instance,
                             klass_pk=obj.pk,
                             index_changes=obj.index_changes,
                             concurrently=settings.CREATE_INDEXES_CONCURRENTLY,
                             record_done=self.index_changes_done)

    def save_object(self, obj):
        obj.unlock(self.index_changes_done)


@register_task
class DeleteKlassIndexesTask(TaskLockMixin, InstanceBasedTask):
    lock_blocking_timeout = None

    def get_lock_key(self, *args, **kwargs):
        return INDEX_LOCK_KEY_TEMPLATE.format(instance_pk=kwargs['instance_pk'])

    def run(self, klass_pk, **kwargs):
        db = get_instance_db(self.instance)
        cursor = connections[db].cursor()
        cursor.execute(SELECT_INDEX_SQL.format(klass_pk=klass_pk, schema_name=self.instance.schema_name))
        for row in cursor.fetchall():
            cursor.execute(DROP_INDEX_SQL.format(index_name=row[0], concurrently=''))


@register_task
class KlassOperationQueue(InstanceBasedTask):
    max_retries = None
    default_retry_delay = settings.DATA_OBJECT_INDEXING_RETRY

    def run(self, klass_pk, op, op_args=None, **kwargs):
        db = get_instance_db(self.instance)
        with transaction.atomic(db):
            try:
                klass = Klass.objects.select_for_update().get(pk=klass_pk)
            except Klass.DoesNotExist:
                self.get_logger().warning('Cannot process Klass[pk=%s] in %s as it no longer exists.',
                                          klass_pk, self.instance)
                return

            if klass.is_locked:
                raise self.retry()

            if op == 'delete':
                klass.delete()
            elif op == 'cleanup_refs':
                klass.cleanup_refs(save=True)
