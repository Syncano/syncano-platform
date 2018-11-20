# coding=UTF8
import os
import tempfile
from socket import gaierror, gethostbyname

import rapidjson as json
from django.conf import settings
from django.http import Http404, HttpResponse
from django.utils.functional import cached_property
from django.utils.text import get_valid_filename
from munch import Munch
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import detail_route, list_route
from rest_framework.exceptions import MethodNotAllowed, PermissionDenied
from rest_framework.negotiation import DefaultContentNegotiation
from rest_framework.request import Empty
from rest_framework.response import Response
from rest_framework_extensions.mixins import DetailSerializerMixin
from retrying import retry

from apps.apikeys.models import ApiKey
from apps.async_tasks.exceptions import UwsgiValueError
from apps.billing.models import AdminLimit
from apps.billing.permissions import OwnerInGoodStanding
from apps.channels.models import Channel
from apps.codeboxes.models import CodeBox
from apps.codeboxes.runtimes import LATEST_NODEJS_RUNTIME
from apps.codeboxes.v1.views import TraceViewSet
from apps.core.authentication import ApiKeyAuthentication
from apps.core.exceptions import RequestLimitExceeded
from apps.core.helpers import Cached, get_tracing_attrs, redis, run_api_view
from apps.core.mixins.views import (
    AtomicMixin,
    CacheableObjectMixin,
    EndpointViewSetMixin,
    NestedViewSetMixin,
    ValidateRequestSizeMixin
)
from apps.core.zipkin import propagate_uwsgi_params
from apps.instances.mixins import InstanceBasedMixin
from apps.instances.models import Instance
from apps.instances.throttling import InstanceRateThrottle
from apps.sockets.exceptions import (
    ChannelFormatKeyError,
    ChannelTooLong,
    SocketCountExceeded,
    SocketEnvironmentFailure,
    SocketEnvironmentNotReady,
    SocketLocked,
    SocketWithUrlRequired
)
from apps.sockets.models import Socket, SocketEndpoint, SocketEndpointTrace, SocketEnvironment, SocketHandler
from apps.sockets.permissions import CheckEndpointAclPermission
from apps.sockets.processor import ScheduleEventHandlerDependency
from apps.sockets.tasks import SocketCheckerTask, SocketProcessorTask
from apps.sockets.v2.serializers import (
    SocketDetailSerializer,
    SocketEndpointSerializer,
    SocketEndpointTraceDetailSerializer,
    SocketEndpointTraceSerializer,
    SocketEnvironmentDetailSerializer,
    SocketEnvironmentSerializer,
    SocketHandlerSerializer,
    SocketLoadSerializer,
    SocketSerializer
)
from apps.webhooks.mixins import AsyncScriptRunnerMixin

try:
    # try to import uwsgi first as that module is not be available outside of uwsgi context (e.g. during tests)
    import uwsgi
except ImportError:
    uwsgi = None


ENDPOINT_CACHE_KEY_TEMPLATE = '{schema}:cache:s:{name}:{hash}'


class SocketViewSet(ValidateRequestSizeMixin, DetailSerializerMixin, AtomicMixin,
                    InstanceBasedMixin, viewsets.ModelViewSet):
    model = Socket
    queryset = Socket.objects.all()
    lookup_field = 'name'
    serializer_class = SocketSerializer
    serializer_detail_class = SocketDetailSerializer
    request_limit = settings.SOCKETS_MAX_ZIP_FILE_SIZE
    throttle_scope = None

    @detail_route(methods=['post'], serializer_detail_class=serializers.Serializer, url_path='update')
    def update_route(self, request, *args, **kwargs):
        socket = self.get_object()
        if not socket.install_url:
            raise SocketWithUrlRequired()
        if socket.is_locked:
            raise SocketLocked()

        socket.update()
        return Response(status=status.HTTP_200_OK,
                        data=self.serializer_class(socket,
                                                   context=self.get_serializer_context()).data)

    @detail_route(methods=['get'],
                  serializer_detail_class=serializers.Serializer,
                  throttle_scope='zip_file')
    def zip_file(self, request, *args, **kwargs):
        socket = self.get_object()
        real_file_list = {f_key: request.build_absolute_uri(Socket.get_storage().url(f_val['file']))
                          for f_key, f_val in socket.file_list.items() if not f_key.startswith('<')}

        # File list with full urls can get quite big so we pass it through tempfile
        with tempfile.NamedTemporaryFile(delete=False, suffix='.file_list', mode="w") as list_file:
            json.dump(real_file_list, list_file)

        try:
            propagate_uwsgi_params(get_tracing_attrs())

            uwsgi.add_var('OFFLOAD_HANDLER', 'apps.sockets.handlers.SocketZipHandler')
            uwsgi.add_var('LIST_FILE', list_file.name)
            uwsgi.add_var('FILE_NAME', get_valid_filename('{}_{}'.format(socket.name, socket.version)))
        except ValueError:
            os.unlink(list_file.name)
            raise UwsgiValueError()
        return HttpResponse()

    @list_route(methods=['post'], serializer_class=SocketLoadSerializer)
    def install(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    def perform_create(self, serializer):
        # Lock on instance for the duration of transaction to avoid race conditions
        with Instance.lock(self.request.instance.pk):
            socket_limit = AdminLimit.get_for_admin(self.request.instance.owner_id).get_sockets_count()
            if Socket.objects.count() >= socket_limit:
                raise SocketCountExceeded(socket_limit)
            serializer.save()

    def perform_update(self, serializer):
        socket = serializer.instance
        if socket.is_locked:
            # Retry process to make sure it runs ok.
            if socket.status == Socket.STATUSES.CHECKING:
                SocketCheckerTask.delay(instance_pk=self.request.instance.pk)
            elif socket.status == Socket.STATUSES.PROCESSING:
                SocketProcessorTask.delay(instance_pk=self.request.instance.pk)

            raise SocketLocked()

        old_env = socket.environment
        super().perform_update(serializer)
        self.check_environment(socket.pk, old_env, socket.environment_id)

    def check_environment(self, socket_pk, old_env, new_env_pk):
        # Remove socket environments if they are no longer used.
        if old_env and old_env.pk != new_env_pk and \
                not Socket.objects.filter(environment=old_env.pk).exclude(pk=socket_pk).exists():
            old_env.delete()

    def perform_destroy(self, instance):
        if instance.is_locked:
            raise SocketLocked()

        super().perform_destroy(instance)
        self.check_environment(instance.pk, instance.environment, None)


class SocketEndpointViewSet(CacheableObjectMixin,
                            AsyncScriptRunnerMixin,
                            InstanceBasedMixin,
                            EndpointViewSetMixin,
                            viewsets.ReadOnlyModelViewSet):
    model = SocketEndpoint
    queryset = SocketEndpoint.objects.select_related('socket')
    lookup_field = 'name'
    serializer_class = SocketEndpointSerializer
    lookup_value_regex = '.+'
    script_task_class = 'apps.sockets.tasks.AsyncScriptTask'
    request_limit = settings.SOCKETS_MAX_PAYLOAD
    trace_type = 'socket_endpoint'

    permission_classes = (
        # Check API Key ACL on object level
        CheckEndpointAclPermission,
        OwnerInGoodStanding,
    )
    throttle_classes = (InstanceRateThrottle,)
    content_negotiation_class = DefaultContentNegotiation

    def initial(self, request, *args, **kwargs):
        # Clear request data when content type == multipart/form-data so it does not get consumed too soon.
        request._empty_data = False
        if request.content_type.startswith('multipart/form-data'):
            request._full_data = {}
            request._empty_data = True

        elif self.get_request_content_length(request) > settings.SOCKETS_MAX_PARSED_PAYLOAD:
            raise RequestLimitExceeded(settings.SOCKETS_MAX_PARSED_PAYLOAD)

        super().initial(request, *args, **kwargs)

    def get_queryset(self):
        base_query = super().get_queryset()

        name = self.kwargs.get('name')
        if name and '/' not in name:
            return base_query.filter(socket__name=name)
        return base_query

    def create_trace(self, meta, args, executed_by_staff, obj, **kwargs):
        return SocketEndpointTrace.create(meta=meta,
                                          args=args,
                                          executed_by_staff=executed_by_staff,
                                          socket_endpoint=kwargs['endpoint'])

    def run_script_view(self, request, endpoint, path, **kwargs):
        # Use method specific metadata if defined, default to full metadata info
        metadata = endpoint.metadata.get(self.request.method, endpoint.metadata)
        socket = endpoint.socket = Cached(Socket, kwargs={'pk': endpoint.socket_id}).get()

        if socket.is_new_format:
            return self.run_codebox_script(request, socket, endpoint, metadata, path, **kwargs)

        # If it was skipped, set full data to Empty so it does get parsed and consumed.
        if request._empty_data:
            request._full_data = Empty

        # Old sockets have lower payload limit.
        if self.get_request_content_length(request) > settings.SOCKETS_MAX_PARSED_PAYLOAD:
            raise RequestLimitExceeded(settings.SOCKETS_MAX_PARSED_PAYLOAD)

        try:
            script = Cached(CodeBox, kwargs={'socket': endpoint.socket_id, 'path': path}).get()
        except CodeBox.DoesNotExist:
            raise Http404()
        return self.run_view(request, obj=endpoint, script=script, metadata=metadata, endpoint=endpoint)

    @cached_property
    @retry(retry_on_exception=lambda x: isinstance(x, gaierror), stop_max_attempt_number=3)
    def get_codebox_handler(self):
        # Get codebox handler ip:port (resolve dns)
        addr, port = settings.CODEBOX_BROKER_UWSGI.split(':')
        codebox_handler = '{}:{}'.format(gethostbyname(addr), port)
        return codebox_handler

    def run_codebox_script(self, request, socket, endpoint, metadata, path, **kwargs):
        skip_payload = request._empty_data

        # Skip payload if we're dealing with small text/plain requests
        # (for backwards compatibility when depending on META.user, META.admin)
        uwsgi.add_var('PAYLOAD_PARSED', '0' if skip_payload else '1')

        script = Munch(config={'allow_full_access': True,
                               'timeout': metadata.get('timeout', settings.SOCKETS_DEFAULT_TIMEOUT)},
                       runtime_name=kwargs.get('runtime', LATEST_NODEJS_RUNTIME),
                       source='')

        if path in socket.file_list:
            # Prepare spec.
            script_files = socket.get_files()
            entrypoint = socket.get_local_path(path)
            spec = {
                'files': script_files,
                'source_hash': socket.get_hash(),
                'entrypoint': entrypoint,
                'output_limit': settings.SOCKETS_MAX_RESULT_SIZE,
                'name': endpoint.name,
            }

            # Add cache param
            try:
                cache = float(metadata.pop('cache'))
                if settings.SOCKETS_MAX_CACHE_TIME >= cache > 0:
                    spec['cache'] = cache
            except (ValueError, KeyError):
                pass

            # Add environment
            if socket.environment_id:
                environment = Cached(SocketEnvironment, kwargs={'pk': socket.environment_id}).get()
                if not environment.is_ready:
                    if environment.status == SocketEnvironment.STATUSES.ERROR:
                        raise SocketEnvironmentFailure()
                    raise SocketEnvironmentNotReady()

                spec['environment'] = environment.get_hash()
                spec['environment_url'] = environment.get_url()

            return self.run_view(request, obj=endpoint, script=script, metadata=metadata, endpoint=endpoint,
                                 spec=spec,
                                 skip_payload=skip_payload, flat_args=True,
                                 uwsgi_handler=self.get_codebox_handler)

    def run_channel_view(self, request, endpoint, channel, viewname='channel-subscribe', **kwargs):
        request._request.GET = request.query_params.copy()

        try:
            room = SocketEndpoint.create_channel_room_name(channel, request)
        except KeyError:
            if '{user}' in channel:
                raise PermissionDenied()
            raise ChannelFormatKeyError()

        if len(room) > settings.CHANNEL_MAX_ROOM_LENGTH:
            raise ChannelTooLong(settings.CHANNEL_MAX_ROOM_LENGTH)

        request.query_params['room'] = room
        return run_api_view(viewname, (request.instance.name, Channel.DEFAULT_NAME),
                            request, **kwargs)

    def match_call(self, calls):
        method = self.request.method
        for call in calls:
            if call['methods'] == ['*'] or method in call['methods']:
                return call
        raise MethodNotAllowed(method)

    def process_endpoint(self, allowed_types=None, **kwargs):
        name = self.kwargs['name']
        if '/' not in name:
            return self.list(self.request)

        endpoint = self.get_object()
        call = self.match_call(endpoint.calls)
        call.update(kwargs)

        # Check if we are processing a correct endpoint type
        if allowed_types is not None and call['type'] not in allowed_types:
            raise PermissionDenied()

        # Deny access if endpoint is private and is accessed without an api_key
        if call.get('private', False) and not self.request.user.is_authenticated and not self.request.auth:
            raise PermissionDenied()

        # Skip checks in nested view, assign bogus apikey
        self.request.auth = ApiKey(instance=self.request.instance, ignore_acl=True)
        self.request.auth_user = self.request.auth_user or ApiKeyAuthentication.get_auth_user(self.request)

        if call['type'] == 'channel':
            return self.run_channel_view(self.request, endpoint, **call)
        return self.run_script_view(self.request, endpoint, **call)

    @detail_route(methods=['get'])
    def history(self, request, *args, **kwargs):
        return self.process_endpoint(allowed_types={'channel'}, viewname='change-list')

    @detail_route(methods=['post'],
                  serializer_class=serializers.Serializer)
    def invalidate(self, request, *args, **kwargs):
        endpoint = self.get_object()
        socket = Cached(Socket, kwargs={'pk': endpoint.socket_id}).get()

        cache_key = ENDPOINT_CACHE_KEY_TEMPLATE.format(
            schema=request.instance.pk,
            name=endpoint.name,
            hash=socket.get_hash(),
        )
        redis.delete(cache_key)
        return HttpResponse(status=status.HTTP_204_NO_CONTENT)


class SocketEndpointTraceViewSet(DetailSerializerMixin, TraceViewSet):
    list_deferred_fields = {'result', 'args'}
    model = SocketEndpointTrace
    serializer_class = SocketEndpointTraceSerializer
    serializer_detail_class = SocketEndpointTraceDetailSerializer


class SocketHandlerViewSet(NestedViewSetMixin,
                           InstanceBasedMixin,
                           viewsets.ReadOnlyModelViewSet):
    model = SocketHandler
    queryset = SocketHandler.objects.all()
    serializer_class = SocketHandlerSerializer

    @detail_route(methods=['get'])
    def traces(self, request, *args, **kwargs):
        obj = self.get_object()
        if obj.handler['type'] == ScheduleEventHandlerDependency.socket_type:
            viewname = 'schedule-trace-list'
        else:
            viewname = 'trigger-trace-list'

        return run_api_view(viewname,
                            (request.instance.name, obj.handler['object_pk']),
                            request, **kwargs)


class SocketEnvironmentViewSet(ValidateRequestSizeMixin, DetailSerializerMixin, AtomicMixin,
                               InstanceBasedMixin,
                               mixins.CreateModelMixin,
                               mixins.RetrieveModelMixin,
                               mixins.UpdateModelMixin,
                               mixins.ListModelMixin,
                               viewsets.GenericViewSet):
    model = SocketEnvironment
    queryset = SocketEnvironment.objects.all()
    lookup_field = 'name'
    serializer_class = SocketEnvironmentSerializer
    serializer_detail_class = SocketEnvironmentDetailSerializer
    request_limit = settings.SOCKETS_MAX_ENVIRONMENT_SIZE

    def perform_create(self, serializer):
        # Lock on instance for the duration of transaction to avoid race conditions
        with Instance.lock(self.request.instance.pk):
            socket_limit = AdminLimit.get_for_admin(self.request.instance.owner_id).get_sockets_count()
            if SocketEnvironment.objects.count() >= socket_limit:
                raise SocketCountExceeded(socket_limit)
            serializer.save()

    def perform_update(self, serializer):
        env = serializer.instance
        if env.is_locked:
            raise SocketLocked()
        super().perform_update(serializer)
