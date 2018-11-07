# coding=UTF8
import rapidjson as json
from django.http import HttpResponse

from apps.async_tasks.exceptions import UwsgiValueError
from apps.batch.decorators import disallow_batching
from apps.core.helpers import get_tracing_attrs, redis
from apps.core.mixins.views import ValidateRequestSizeMixin
from apps.core.zipkin import propagate_uwsgi_params
from apps.sockets.tasks import AsyncScriptTask
from apps.webhooks.exceptions import UnsupportedPayload
from apps.webhooks.helpers import prepare_payload_data, strip_meta_from_uwsgi_info
from apps.webhooks.models import WebhookTrace
from apps.webhooks.v1.serializers import WebhookRunSerializer

try:
    # try to import uwsgi first as that module is not be available outside of uwsgi context (e.g. during tests)
    import uwsgi
except ImportError:
    uwsgi = None

PAYLOAD_TEMPLATE = 'script:payload:{instance_pk}:{trace_type}:{trace_pk}'
METADATA_TEMPLATE = 'script:meta:{instance_pk}:{trace_type}:{trace_pk}'
PAYLOAD_TIMEOUT = 2 * 60 * 60  # 2 hours


class AsyncScriptRunnerMixin(ValidateRequestSizeMixin):
    trace_type = 'webhook'
    cache_response = False
    script_task_class = 'apps.webhooks.tasks.WebhookTask'
    offload_handler_class = 'apps.webhooks.handlers.WebhookHandler'

    @classmethod
    def get_response(cls, content):
        return HttpResponse(**content)

    def create_trace(self, meta, args, executed_by_staff, obj, **kwargs):
        raise NotImplementedError  # pragma: no cover

    def get_payload(self, request, flat_args=False):
        data = prepare_payload_data(request)
        serializer = WebhookRunSerializer(data=data)
        serializer.is_valid(raise_exception=True)

        payload = serializer.data
        trace_args = payload.copy()

        # Combine arguments and make them flat
        args = {}
        for value in list(payload.values()):
            if isinstance(value, dict):
                args.update(value)

        if flat_args:
            payload = args
        else:
            payload.update(args)

        try:
            payload_data = json.dumps(payload)
        except (OverflowError, UnicodeDecodeError):
            raise UnsupportedPayload()
        return payload_data, trace_args

    @disallow_batching
    def run_view(self, request, *args, **kwargs):
        if 'obj' in kwargs:
            obj = kwargs.pop('obj')
        else:
            obj = self.get_object()

        instance = request.instance
        offload_handler_class = kwargs.get('offload_handler_class')
        uwsgi_handler = kwargs.get('uwsgi_handler')
        payload_data = None

        if kwargs.get('skip_payload', False):
            trace_args = request.query_params.dict()
        else:
            flat_args = kwargs.get('flat_args', False) or instance.created_at.year >= 2017 or \
                (hasattr(obj, 'created_at') and obj.created_at.year >= 2017)
            payload_data, trace_args = self.get_payload(request, flat_args=flat_args)

        request_meta = strip_meta_from_uwsgi_info(request.META)

        # we use getattr below because webhook can be called
        # from public view without authentication_classes
        as_staff = getattr(request, 'staff_user', None) is not None

        trace = self.create_trace(meta=request_meta, args=trace_args, executed_by_staff=as_staff, obj=obj, **kwargs)

        meta = {'request': request_meta, 'metadata': kwargs.get('metadata', {})}
        user = getattr(request, 'auth_user', None)
        if user:
            meta['user'] = {
                'id': user.id,
                'username': user.username,
                'user_key': user.key
            }
        admin = getattr(request, 'user', None)
        if admin.is_authenticated:
            meta['admin'] = {
                'id': admin.id,
                'email': admin.email,
            }

        spec = kwargs.get('spec')
        if spec is None:
            # Save payload and meta to redis
            payload_key = None
            if payload_data is not None:
                payload_key = PAYLOAD_TEMPLATE.format(instance_pk=instance.pk,
                                                      trace_type=self.trace_type,
                                                      trace_pk=trace.pk)
                redis.set(payload_key, payload_data, ex=PAYLOAD_TIMEOUT)

            meta_key = METADATA_TEMPLATE.format(instance_pk=instance.pk,
                                                trace_type=self.trace_type,
                                                trace_pk=trace.pk)
            redis.set(meta_key, json.dumps(meta), ex=PAYLOAD_TIMEOUT)
            return self.create_uwsgi_response(request, obj, instance, trace, payload_key, meta_key,
                                              script=kwargs.get('script'),
                                              offload_handler_class=offload_handler_class,
                                              uwsgi_handler=uwsgi_handler)

        # TODO: sockets only?
        meta.update({'executed_by': AsyncScriptTask.trace_type, 'executor': obj.name, 'instance': instance.name})
        trace_spec = AsyncScriptTask.create_trace_spec(instance, obj=obj, trace_pk=trace.pk)

        task_spec = AsyncScriptTask.create_script_spec(instance, kwargs['script'], payload_data, meta, '', trace_spec,
                                                       obj.socket)
        spec.update(task_spec)

        # Save spec to redis
        payload_key = PAYLOAD_TEMPLATE.format(instance_pk=instance.pk,
                                              trace_type=self.trace_type,
                                              trace_pk=trace.pk)
        redis.set(payload_key, json.dumps(spec), ex=PAYLOAD_TIMEOUT)
        return self.create_uwsgi_response(request, obj, instance, trace, payload_key,
                                          offload_handler_class=offload_handler_class,
                                          uwsgi_handler=uwsgi_handler)

    def create_uwsgi_response(self, request, obj, instance, trace, payload_key, meta_key=None, script=None,
                              offload_handler_class=None, uwsgi_handler=None):
        try:
            propagate_uwsgi_params(get_tracing_attrs())

            if uwsgi_handler is not None:
                uwsgi.add_var('UWSGI_HANDLER', uwsgi_handler)
            else:
                uwsgi.add_var('OFFLOAD_HANDLER', offload_handler_class or self.offload_handler_class)
                uwsgi.add_var('TASK_CLASS', self.script_task_class)

            uwsgi.add_var('OBJECT_PK', str(obj.pk))
            uwsgi.add_var('INSTANCE_PK', str(instance.pk))
            uwsgi.add_var('TRACE_PK', str(trace.pk))
            uwsgi.add_var('PAYLOAD_KEY', payload_key)

            response_template = getattr(request, 'response_template', None)
            if response_template:
                uwsgi.add_var('TEMPLATE', response_template.name)

            if meta_key is not None:
                uwsgi.add_var('META_KEY', str(meta_key))

            if script:
                uwsgi.add_var('SCRIPT_PK', str(script.pk))
        except ValueError:
            raise UwsgiValueError()
        return HttpResponse()


class RunWebhookMixin(AsyncScriptRunnerMixin):
    def create_trace(self, meta, args, executed_by_staff, obj, **kwargs):
        return WebhookTrace.create(meta=meta, args=args, executed_by_staff=executed_by_staff, webhook=obj)
