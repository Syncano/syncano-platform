# coding=UTF8
import time
from datetime import timedelta

import grpc
import rapidjson as json
from django.conf import settings
from django.db import router, transaction
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from munch import Munch
from settings.celeryconf import app, register_task

from apps.admins.models import Admin
from apps.billing.models import AdminLimit
from apps.billing.permissions import OwnerInGoodStanding
from apps.channels.models import Change, Channel
from apps.codeboxes.exceptions import ContainerException
from apps.codeboxes.helpers import get_codebox_spec
from apps.codeboxes.signals import codebox_finished
from apps.codeboxes.v2.serializers import CodeBoxTraceSerializer, ScheduleTraceSerializer
from apps.core.helpers import (
    Cached,
    generate_key,
    get_tracing_attrs,
    iterate_over_queryset_in_chunks,
    make_token,
    redis
)
from apps.core.mixins import TaskLockMixin
from apps.core import zipkin
from apps.instances.helpers import set_current_instance
from apps.instances.models import Instance, InstanceIndicator
from apps.sockets.models import Socket, SocketEnvironment

from .models import CodeBox, CodeBoxSchedule, CodeBoxTrace, ScheduleTrace, Trace
from .runner import CodeBoxRunner

SCHEDULE_TRACE_TIMEOUT = 6 * 60  # 6 minutes
QUEUE_TIMEOUT = 2 * 60 * 60  # 2 hours
CODEBOX_COUNTER_TIMEOUT = 2 * settings.CODEBOX_MAX_TIMEOUT

PERIODIC_SCHEDULE_TEMPLATE = 'codebox:schedule:{instance_pk}-{schedule_pk}:{scheduled_at}'
CODEBOX_COUNTER_TEMPLATE = "codebox:instance:{instance}:counter"
QUEUE_PRIORITY_TEMPLATE = "codebox:instance:{instance}:priority_queue"
QUEUE_TEMPLATE = "codebox:instance:{instance}:queue"
SPEC_TEMPLATE = 'codebox:spec:{instance_pk}:{incentive_pk}:{spec_id}'
SPEC_TIMEOUT = 30 * 60  # 30 minutes
GRPC_RUN_TIMEOUT = 5


def _get_instance(instance_pk):
    try:
        return Cached(Instance, kwargs=dict(pk=instance_pk)).get()
    except Instance.DoesNotExist:
        pass


@register_task
class CodeBoxRunTask(app.Task):
    default_retry_delay = 1

    def run(self, instance_pk, concurrency_limit):
        limit_key = CODEBOX_COUNTER_TEMPLATE.format(instance=instance_pk)

        # Check counter if I can run
        if not self.can_run(limit_key, limit=concurrency_limit):
            return

        priority_queue = QUEUE_PRIORITY_TEMPLATE.format(instance=instance_pk)
        normal_queue = QUEUE_TEMPLATE.format(instance=instance_pk)
        queue = priority_queue

        try:
            spec_key = redis.lpop(queue)
            if spec_key is None:
                queue = normal_queue
                spec_key = redis.lpop(queue)

            if spec_key is not None:
                self.process_spec(spec_key, queue)
        finally:
            self.cleanup(limit_key)
            if redis.llen(priority_queue) > 0 or redis.llen(normal_queue) > 0:
                # Requeue itself if needed
                self.delay(instance_pk, concurrency_limit)

    def can_run(self, limit_key, limit):
        if redis.incr(limit_key) > limit:
            redis.decr(limit_key)
            return False
        else:
            redis.expire(limit_key, CODEBOX_COUNTER_TIMEOUT)
        return True

    def cleanup(self, limit_key):
        if redis.decr(limit_key) < 0:
            redis.delete(limit_key)
        else:
            redis.expire(limit_key, CODEBOX_COUNTER_TIMEOUT)

    def process_spec(self, spec_key, queue=None):
        logger = self.get_logger()
        runner = CodeBoxRunner(logger=logger)

        codebox_spec = get_codebox_spec(spec_key)
        if codebox_spec is None:
            logger.warning("CodeBox spec has expired. Nothing to do here.")
            return

        expire_at = codebox_spec.get('expire_at')
        if expire_at:
            now = timezone.now()
            expire_at = parse_datetime(expire_at)

            if now > expire_at:
                if 'trace' in codebox_spec:
                    SaveTraceTask.delay(codebox_spec['trace'], {
                        'status': Trace.STATUS_CHOICES.QUEUE_TIMEOUT,
                        'executed_at': now.strftime(settings.DATETIME_FORMAT),
                        'result': {'stdout': '', 'stderr': 'Internal queue timeout.'}
                    })
                logger.warning("CodeBox spec runtime has expired.")
                return

        try:
            runner.run(codebox_spec)
        except (ContainerException, IOError, FileNotFoundError) as exc:
            # Put it at the beginning of queue, still log the error as we should try to fix it.
            if isinstance(exc, ContainerException):
                self.get_logger().exception(exc)
            if queue is not None:
                redis.lpush(queue, spec_key)
        except Exception as exc:
            self.get_logger().exception(exc)
        else:
            redis.delete(spec_key)


class BaseIncentiveTask(app.Task):
    default_retry_delay = 1
    grpc_run_retries = 5
    incentive_class = None
    trace_type = None
    trace_class = None
    serializer_class = None
    max_timeout = settings.CODEBOX_MAX_TIMEOUT
    default_timeout = settings.CODEBOX_DEFAULT_TIMEOUT

    channel = None
    runner = None

    trace_type_map = {}

    def __new__(cls, *args, **kwargs):
        cls.trace_type_map[cls.trace_type] = cls
        return super().__new__(cls, *args, **kwargs)

    @classmethod
    def create_spec(cls, *args, **kwargs):
        raise NotImplementedError  # pragma: no cover

    @classmethod
    def create_run_spec(cls, instance, codebox, additional_args, meta, dumps=True, socket=None):
        custom_timeout = codebox.config.pop('timeout', None)
        async_mode = codebox.config.pop('async', 0)
        mcpu = codebox.config.pop('mcpu', 0)
        timeout = cls.default_timeout

        if custom_timeout and isinstance(custom_timeout, (int, float)) and custom_timeout > 0:
            timeout = min(cls.max_timeout, custom_timeout)

        if dumps:
            additional_args = json.dumps(additional_args or {})
        else:
            additional_args = additional_args or "{}"

        config = instance.config.copy()
        if socket:
            config.update(socket.config)
            meta['socket'] = socket.name
        config.update(codebox.config)

        # Add token if allow_full_access is True
        if config.pop('allow_full_access', False) is True:
            meta['token'] = make_token(instance)
        meta['api_host'] = settings.API_HOST
        if settings.SPACE_HOST:
            meta['space_host'] = settings.SPACE_HOST
        meta['async'] = async_mode

        return {
            'instance': instance.name,
            'runtime_name': codebox.runtime_name,
            'original_source': codebox.source,
            'config': json.dumps(config),
            'timeout': timeout,
            'async': async_mode,
            'mcpu': mcpu,
            'additional_args': additional_args,
            'meta': json.dumps(meta),
            'concurrency_limit': AdminLimit.get_for_admin(instance.owner_id).get_codebox_concurrency(),
        }

    @classmethod
    def create_trace_spec(cls, instance, obj, trace_pk=None):
        spec = {
            'id': trace_pk,
            'type': cls.trace_type,
            'instance_id': instance.pk,
            'obj_id': obj.pk,
            'obj_name': getattr(obj, 'name', None),
        }
        if obj.socket:
            spec['socket'] = obj.socket.name
        return spec

    @classmethod
    def publish_codebox_spec(cls, instance_pk, incentive_pk, spec):
        serialized_spec = json.dumps(spec)
        spec_id = generate_key()
        spec_key = SPEC_TEMPLATE.format(instance_pk=instance_pk, incentive_pk=incentive_pk, spec_id=spec_id)
        redis.set(spec_key, serialized_spec, SPEC_TIMEOUT)
        return spec_key

    def is_incentive_valid(self, instance, incentive, **kwargs):
        return True

    def is_incentive_priority(self, instance, incentive):
        return False

    def get_incentive(self, instance, incentive_pk):
        set_current_instance(instance)

        try:
            incentive = Cached(self.incentive_class, kwargs={'pk': incentive_pk}).get()
        except self.incentive_class.DoesNotExist:
            self.get_logger().warning(
                "%s[pk=%s] for %s cannot be run, because script was not found.",
                self.incentive_class.__name__, incentive_pk, instance)
            return None

        if hasattr(incentive, 'codebox_id'):
            try:
                incentive.codebox = Cached(CodeBox, kwargs={'pk': incentive.codebox_id}).get()
            except CodeBox.DoesNotExist:
                self.get_logger().warning(
                    "%s[pk=%s] for %s cannot be run, because script was not found.",
                    self.incentive_class.__name__, incentive.pk, instance)
                return None

        socket = None
        if incentive.socket_id:
            try:
                socket = Cached(Socket, kwargs={'pk': incentive.socket_id}).get()
            except Socket.DoesNotExist:
                pass
        incentive.socket = socket
        return incentive

    def block_run(self, message, incentive, instance, spec, status=Trace.STATUS_CHOICES.BLOCKED):
        self.get_logger().warning(message,
                                  incentive,
                                  instance)

        SaveTraceTask.delay(spec['trace'], {
            'status': status,
            'executed_at': timezone.now().strftime(settings.DATETIME_FORMAT),
        })

    def process_grpc(self, instance, incentive, spec):
        logger = self.get_logger()
        from apps.codeboxes.proto import broker_pb2, broker_pb2_grpc

        if self.runner is None:
            self.channel = grpc.insecure_channel(settings.CODEBOX_BROKER_GRPC, settings.CODEBOX_GRPC_OPTIONS)
            self.runner = broker_pb2_grpc.ScriptRunnerStub(self.channel)
        socket = incentive.socket

        entrypoint = socket.get_local_path(incentive.codebox.path)

        # Add environment
        environment_hash = ''
        environment_url = ''
        if socket.environment_id:
            environment = Cached(SocketEnvironment, kwargs={'pk': socket.environment_id}).get()
            if not environment.is_ready:
                self.block_run('Environment is not yet ready.',
                               incentive, instance, spec,
                               status=Trace.STATUS_CHOICES.FAILURE)
                return

            environment_hash = environment.get_hash()
            environment_url = environment.get_url()

        req = broker_pb2.RunRequest(
            meta={
                'files': socket.get_files(),
                'environmentURL': environment_url,
                'trace': json.dumps(spec['trace']).encode(),
                'traceID': spec['trace']['id'],
            },
            lbMeta={
                'concurrencyKey': str(instance.pk),
                'concurrencyLimit': spec['run']['concurrency_limit'],
            },
            request=[{
                'meta': {
                    'runtime': spec['run']['runtime_name'],
                    'sourceHash': socket.get_hash(),
                    'userID': str(instance.pk),
                    'environment': environment_hash,
                    'options': {
                        'entryPoint': entrypoint,
                        'outputLimit': settings.CODEBOX_RESULT_SIZE_LIMIT,
                        'timeout': int(spec['run']['timeout'] * 1000),
                        'async': spec['run']['async'],
                        'mCPU': spec['run']['mcpu'],
                        'args': spec['run']['additional_args'].encode(),
                        'config': spec['run']['config'].encode(),
                        'meta': spec['run']['meta'].encode(),
                    },
                },
            }]
        )

        # Retry grpc Run if needed.
        metadata = zipkin.create_headers_from_zipkin_attrs(get_tracing_attrs()).items()

        for i in range(self.grpc_run_retries + 1):
            try:
                response = self.runner.Run(req, timeout=GRPC_RUN_TIMEOUT, metadata=metadata)
                for _ in response:
                    # Drain response so it is processed and not queued
                    pass
                return
            except Exception:
                if i + 1 > self.grpc_run_retries:
                    raise
                logger.warning("gRPC run failed, retrying (try #%d out of %d)", i + 1, self.grpc_run_retries,
                               exc_info=1)
                time.sleep(1)

    def process(self, instance_pk, incentive_pk, **kwargs):
        logger = self.get_logger()
        instance = _get_instance(instance_pk)
        if instance is None:
            logger.warning(
                "%s[pk=%s] for %s cannot be run, because instance was not found.",
                self.incentive_class.__name__, incentive_pk, instance)
            return

        incentive = self.get_incentive(instance, incentive_pk)
        if not incentive or not self.is_incentive_valid(instance, incentive, **kwargs):
            return

        spec = self.create_spec(instance, incentive, **kwargs)
        if not OwnerInGoodStanding.is_admin_in_good_standing(instance.owner_id):
            self.block_run('Blocked %s for %s, instance owner cannot run new codeboxes.',
                           incentive, instance, spec)
            return

        # If legacy codeboxes are disabled, only allow new socket format.
        if not settings.LEGACY_CODEBOX_ENABLED and (incentive.socket is None or not incentive.socket.is_new_format):
            self.block_run('Blocked %s for %s, legacy codeboxes are disabled.',
                           incentive, instance, spec)
            return

        logger.info('Running %s for %s.', incentive, instance)

        if incentive.socket is not None and incentive.socket.is_new_format:
            self.process_grpc(instance, incentive, spec)
            return

        spec_key = self.publish_codebox_spec(instance_pk, incentive_pk, spec)
        if self.is_incentive_priority(instance, incentive):
            queue = QUEUE_PRIORITY_TEMPLATE.format(instance=instance_pk)
        else:
            queue = QUEUE_TEMPLATE.format(instance=instance_pk)

        concurrency_limit = spec['run']['concurrency_limit']
        if redis.llen(queue) >= settings.CODEBOX_QUEUE_LIMIT_PER_RUNNER * concurrency_limit:
            self.block_run('Blocked %s for %s, queue limit exceeded.',
                           incentive, instance, spec)
            return

        redis.rpush(queue, spec_key)
        redis.expire(queue, QUEUE_TIMEOUT)

        # Wake up codebox runner
        CodeBoxRunTask.delay(instance_pk=instance.pk, concurrency_limit=concurrency_limit)


@register_task
class CodeBoxTask(BaseIncentiveTask):
    incentive_class = CodeBox
    trace_type = 'codebox'
    trace_class = CodeBoxTrace
    serializer_class = CodeBoxTraceSerializer

    @classmethod
    def create_spec(cls, instance, codebox, additional_args, trace_pk, *args, **kwargs):
        meta = {'executed_by': 'codebox', 'executor': codebox.id, 'instance': instance.name}
        codebox_spec = {
            'run': cls.create_run_spec(instance, codebox, additional_args, meta, socket=codebox.socket),
            'trace': cls.create_trace_spec(instance, obj=codebox, trace_pk=trace_pk)
        }
        return codebox_spec

    def run(self, incentive_pk, instance_pk, additional_args=None, trace_pk=None):
        self.process(instance_pk=instance_pk,
                     incentive_pk=incentive_pk,
                     additional_args=additional_args,
                     trace_pk=trace_pk)


@register_task
class ScheduleTask(BaseIncentiveTask):
    incentive_class = CodeBoxSchedule
    trace_type = 'schedule'
    trace_class = ScheduleTrace
    serializer_class = ScheduleTraceSerializer
    max_timeout = settings.SCHEDULE_MAX_TIMEOUT
    default_timeout = settings.SCHEDULE_DEFAULT_TIMEOUT

    @classmethod
    def create_spec(cls, instance, schedule, *args, **kwargs):
        codebox = schedule.codebox
        trace_spec = cls.create_trace_spec(instance, obj=schedule)
        trace_spec['event_handler'] = schedule.event_handler

        meta = {'executed_by': 'schedule', 'executor': schedule.id, 'instance': instance.name}
        codebox_spec = {
            'run': cls.create_run_spec(instance, codebox, None, meta, socket=schedule.socket),
            'trace': trace_spec,
        }
        return codebox_spec

    def run(self, incentive_pk, instance_pk):
        self.process(instance_pk=instance_pk,
                     incentive_pk=incentive_pk)


@register_task
class SchedulerDispatcher(TaskLockMixin, app.Task):
    def run(self):
        schedules_type = InstanceIndicator.TYPES.SCHEDULES_COUNT
        qs = InstanceIndicator.objects.filter(type=schedules_type,
                                              value__gt=0,
                                              instance__location=settings.LOCATION).select_related('instance')

        for chunk_of_pks in iterate_over_queryset_in_chunks(qs, 'instance_id'):
            SchedulerTask.delay(chunk_of_pks)


@register_task
class SchedulerTask(TaskLockMixin, app.Task):
    lock_generate_hash = True

    def run(self, instance_pks):
        for instance_pk in instance_pks:
            instance = _get_instance(instance_pk)
            if instance is None:
                continue

            if not OwnerInGoodStanding.is_admin_in_good_standing(instance.owner_id):
                continue

            set_current_instance(instance)
            schedules = CodeBoxSchedule.objects.get_for_process()
            for schedule in schedules:
                key = PERIODIC_SCHEDULE_TEMPLATE.format(instance_pk=instance.pk, schedule_pk=schedule.pk,
                                                        scheduled_at=schedule.scheduled_next.isoformat())
                can_run = redis.set(name=key, value=1, nx=True, ex=SCHEDULE_TRACE_TIMEOUT)
                if not can_run:
                    time_in_queue = timezone.now() - schedule.scheduled_next
                    if time_in_queue > timedelta(minutes=2):
                        self.get_logger().warning(
                            "%s in %s cannot be run yet, because it was already scheduled for %s, time in queue: %s.",
                            schedule, instance, schedule.scheduled_next.isoformat(), time_in_queue)
                else:
                    ScheduleTask.delay(schedule.id, instance_pk)

            if schedules:
                admin = Cached(Admin, kwargs={'id': instance.owner_id}).get()
                admin.update_last_access()


class TraceBaseTask(app.Task):
    def _get_instance(self, trace_spec):
        logger = self.get_logger()
        instance_id = trace_spec.get('instance_id')
        if not instance_id:
            logger.error("Trace to save without instance_id, trace_spec %s.", trace_spec)
            return None

        instance = _get_instance(instance_id)
        if instance is None:
            logger.warning(
                "Trace %s in Instance[pk=%s] cannot be saved, because instance was not found.",
                trace_spec, instance_id)
            return None

        return instance

    @classmethod
    def _get_trace(cls, trace_spec, trace_class):
        if trace_spec.get('id'):
            return trace_class.get(trace_spec['id'])
        return trace_class()

    @classmethod
    def _get_trace_class(cls, trace_spec):
        return BaseIncentiveTask.trace_type_map[trace_spec['type']].trace_class

    @classmethod
    def _get_serializer_class(cls, trace_spec):
        return BaseIncentiveTask.trace_type_map[trace_spec['type']].serializer_class

    @classmethod
    def _get_trace_context(cls, trace_spec):
        return {trace_spec['type']: Munch(id=trace_spec['obj_id'], name=trace_spec['obj_name'])}


@register_task
class UpdateTraceTask(TraceBaseTask):
    def run(self, trace_spec, status=Trace.STATUS_CHOICES.PROCESSING):
        instance = self._get_instance(trace_spec)
        if not instance:
            return

        set_current_instance(instance)

        # update to processing have only sense if there's a trace already created;
        trace_class = self._get_trace_class(trace_spec)
        trace_class.update(trace_spec['id'],
                           updated={'status': status},
                           expected={'status': trace_class.STATUS_CHOICES.PENDING},
                           **self._get_trace_context(trace_spec))


@register_task
class SaveTraceTask(TraceBaseTask):
    api_version = 'v2'

    def publish_log(self, instance, trace, trace_spec):
        serializer_class = self._get_serializer_class(trace_spec)
        view_kwargs = self._get_trace_context(trace_spec)
        view_kwargs['instance'] = instance

        trace.executed_at = parse_datetime(trace.executed_at)
        payload = serializer_class(trace, excluded_fields=('links',)).data
        trace_self_link = reverse('{}:{}'.format(self.api_version, serializer_class.hyperlinks[0][1]),
                                  args=(instance.name,
                                        trace_spec['obj_name'] or trace_spec['obj_id'],
                                        trace.pk))
        payload['links'] = {'self': trace_self_link}

        socket = trace_spec['socket']
        room = 'socket:{}'.format(socket)
        metadata = {'type': 'trace', 'socket': socket}
        if trace_spec['type'] == 'socket_endpoint':
            metadata['source'] = 'endpoint'
            metadata['endpoint'] = trace_spec['obj_name']
        elif trace_spec['type'] in ('trigger', 'schedule'):
            metadata['source'] = 'event_handler'
            metadata['event_handler'] = trace_spec['event_handler']

        set_current_instance(instance)
        channel = Channel.get_eventlog()

        channel.create_change(room=room,
                              author={},
                              metadata=metadata,
                              payload=payload,
                              action=Change.ACTIONS.CUSTOM)

    def run(self, trace_spec, result_info):
        instance = self._get_instance(trace_spec)
        if not instance:
            return

        set_current_instance(instance)

        trace_class = self._get_trace_class(trace_spec)
        trace = self._get_trace(trace_spec, trace_class)

        for k, v in result_info.items():
            setattr(trace, k, v)

        if not trace._saved:
            # If we're dealing with unsaved object, we need the list key as well so pass kwargs for it
            trace.save(**self._get_trace_context(trace_spec))
        else:
            trace.save(update_fields=result_info.keys())

        if trace_spec['type'] == 'schedule':
            ScheduleNextTask.delay(instance_pk=trace_spec['instance_id'], schedule_id=trace_spec['obj_id'])

        if 'socket' in trace_spec:
            self.publish_log(instance, trace, trace_spec)

        codebox_finished.send(sender=trace_class, instance=instance, object_id=trace_spec['obj_id'], trace=trace)


@register_task
class ScheduleNextTask(app.Task):
    def run(self, instance_pk, schedule_id):
        instance = _get_instance(instance_pk)
        if instance is None:
            return

        set_current_instance(instance)
        using = router.db_for_write(CodeBoxSchedule, instance=self)
        with transaction.atomic(using=using):
            try:
                schedule = CodeBoxSchedule.objects.select_for_update().get(id=schedule_id)
                schedule.schedule_next()
            except CodeBoxSchedule.DoesNotExist:
                pass
