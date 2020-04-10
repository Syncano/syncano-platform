# coding=UTF8
import logging

from django.http import HttpResponse
from rest_condition import And, Or
from rest_framework import status, viewsets
from rest_framework.decorators import detail_route
from rest_framework.response import Response
from rest_framework_extensions.mixins import DetailSerializerMixin

from apps.admins.permissions import AdminHasPermissions
from apps.apikeys.permissions import IsApiKeyAccess, IsApiKeyAllowingAnonymousRead, IsApiKeyIgnoringAcl
from apps.async_tasks.exceptions import UwsgiValueError
from apps.batch.decorators import disallow_batching
from apps.billing.permissions import OwnerInGoodStanding
from apps.channels.exceptions import RoomRequired
from apps.channels.helpers import create_author_dict
from apps.channels.models import Change, Channel
from apps.channels.permissions import (
    EnsureChannelCustomPublish,
    EnsureChannelRoom,
    HasChannelSubscribePermission,
    HasPublishPermission,
    HasSubscribePermission,
    ProtectBuiltinChannel
)
from apps.channels.throttling import ChannelPollRateThrottle
from apps.channels.v1.serializers import (
    ChangeSerializer,
    ChannelDetailSerializer,
    ChannelPublishSerializer,
    ChannelSerializer,
    ChannelSubscribeSerializer
)
from apps.core.helpers import get_current_span_propagation, get_from_request_query_params, propagate_uwsgi_params
from apps.core.mixins.views import (
    AtomicMixin,
    AutocompleteMixin,
    CacheableObjectMixin,
    NestedViewSetMixin,
    ValidateRequestSizeMixin
)
from apps.core.throttling import AnonRateThrottle
from apps.instances.mixins import InstanceBasedMixin
from apps.redis_storage import views as redis_views
from apps.users.permissions import HasUser

try:
    # try to import uwsgi first as that module is not be available outside of uwsgi context (e.g. during tests)
    import uwsgi
except ImportError:
    uwsgi = None

logger = logging.getLogger(__name__)

CHANNEL_PAYLOAD_LIMIT = 64 * 1024


class ChannelViewSet(CacheableObjectMixin,
                     ValidateRequestSizeMixin,
                     AutocompleteMixin,
                     AtomicMixin,
                     InstanceBasedMixin,
                     DetailSerializerMixin,
                     viewsets.ModelViewSet):
    model = Channel
    queryset = Channel.objects.all()
    lookup_field = 'name'
    serializer_class = ChannelSerializer
    serializer_detail_class = ChannelDetailSerializer
    permission_classes = (
        Or(
            AdminHasPermissions,
            And(
                # Otherwise when we're dealing with api key access
                IsApiKeyAccess,
                Or(
                    # Force access when ignoring acl
                    IsApiKeyIgnoringAcl,
                    # Force access when allow annonymous read
                    IsApiKeyAllowingAnonymousRead,
                    And(
                        HasUser, HasSubscribePermission,
                    ),
                ),
            ),
        ),
        ProtectBuiltinChannel,
        OwnerInGoodStanding,
    )

    def get_queryset(self):
        base_query = super().get_queryset()

        if self.request.auth and not self.request.auth.ignore_acl:
            if self.request.auth_user:
                group_perm_query = """
                   channels_channel.other_permissions >= %s OR (
                       channels_channel.group_id IS NOT NULL AND
                       channels_channel.group_permissions >= %s AND
                       EXISTS (
                            SELECT 1
                            FROM users_membership
                            WHERE channels_channel.group_id = users_membership.group_id
                            AND users_membership.user_id = %s
                        )
                    )
                """
                return base_query.extra(where=[group_perm_query],
                                        params=(Channel.PERMISSIONS.SUBSCRIBE.value,
                                                Channel.PERMISSIONS.SUBSCRIBE.value,
                                                self.request.auth_user.id))
            else:
                base_query = base_query.filter(other_permissions__gte=Channel.PERMISSIONS.SUBSCRIBE)
        return base_query

    def create_uwsgi_response(self, request, channel, last_id, room, transport='poll'):
        try:
            propagate_uwsgi_params(get_current_span_propagation())

            if transport == 'poll':
                uwsgi.add_var('OFFLOAD_HANDLER', 'apps.channels.handlers.ChannelPollHandler')
            else:
                uwsgi.add_var('OFFLOAD_HANDLER', 'apps.channels.handlers.ChannelWSHandler')
            uwsgi.add_var('CHANNEL_PK', str(channel.pk))
            uwsgi.add_var('INSTANCE_PK', str(request.instance.pk))
            uwsgi.add_var('STREAM_CHANNEL', channel.get_stream_channel_name(room))

            if room is not None:
                uwsgi.add_var('CHANNEL_ROOM', room)
            if last_id is not None:
                uwsgi.add_var('LAST_ID', str(last_id))
        except ValueError:
            raise UwsgiValueError()
        return HttpResponse()

    @disallow_batching
    @detail_route(methods=['get'],
                  serializer_detail_class=ChannelSubscribeSerializer,
                  throttle_classes=(AnonRateThrottle, ChannelPollRateThrottle,))
    def poll(self, request, *args, **kwargs):
        channel = self.get_object()
        serializer = self.get_serializer(data=request.GET)

        if serializer.is_valid():
            data = serializer.validated_data
            last_id = data.get('last_id')

            # Validate room
            room = None
            if channel.type == Channel.TYPES.SEPARATE_ROOMS:
                room = data.get('room', '').lower()
                if not room:
                    raise RoomRequired()

            # If transport == websocket, fallback to websocket handler
            if request.query_params.get('transport') == 'websocket':
                return self.create_uwsgi_response(request, channel, last_id, room, transport='websocket')

            # Otherwise process polling normally
            return self.process_poll(request, channel, last_id, room)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def process_poll(self, request, channel, last_id, room):
        # Filter by last id if needed
        if last_id is not None:
            # Filter by last_id by id
            change_list = Change.list(min_pk=last_id + 1, ordering='asc', limit=1, channel=channel, room=room)
            if change_list:
                return Response(
                    ChangeSerializer(change_list[0], excluded_fields=('links', 'room',)).data)

        # No results found, return an async_tasks handler to subscribe and wait for results
        return self.create_uwsgi_response(request, channel, last_id, room)

    @detail_route(methods=['post'],
                  serializer_detail_class=ChannelPublishSerializer,
                  permission_classes=(Or(
                      AdminHasPermissions,
                      And(IsApiKeyAccess, Or(IsApiKeyIgnoringAcl, And(HasUser, HasPublishPermission)))
                  ), OwnerInGoodStanding, EnsureChannelCustomPublish),
                  request_limit=CHANNEL_PAYLOAD_LIMIT)
    def publish(self, request, *args, **kwargs):
        channel = self.get_object()
        serializer = self.get_serializer(data=request.data)

        if serializer.is_valid():
            author = create_author_dict(self.request)
            metadata = {'type': 'message'}
            data = serializer.validated_data
            payload = data.get('payload', {})
            room = None

            if channel.type == Channel.TYPES.SEPARATE_ROOMS:
                room = data.get('room')
                if not room:
                    raise RoomRequired()

            change = channel.create_change(room=room,
                                           author=author,
                                           metadata=metadata,
                                           payload=payload,
                                           action=Change.ACTIONS.CUSTOM)

            change.channel = channel
            return Response(ChangeSerializer(change, context=self.get_serializer_context()).data,
                            status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ChangeViewSet(InstanceBasedMixin,
                    NestedViewSetMixin,
                    redis_views.ReadOnlyModelViewSet):
    model = Change
    serializer_class = ChangeSerializer
    permission_classes = (
        Or(
            AdminHasPermissions,
            And(
                IsApiKeyAccess,
                Or(
                    IsApiKeyIgnoringAcl,
                    # Force access when allow anonymous read
                    IsApiKeyAllowingAnonymousRead,
                    And(
                        HasUser, HasChannelSubscribePermission
                    )
                )
            )
        ),
        EnsureChannelRoom,
        OwnerInGoodStanding,
    )

    def initial(self, request, *args, **kwargs):
        self.room, self.last_id = get_from_request_query_params(self.request, 'room', 'last_id')
        if self.last_id:
            try:
                self.last_id = int(self.last_id) + 1
            except ValueError:
                self.last_id = None

        return super().initial(request, *args, **kwargs)

    def list(self, request, *args, **kwargs):
        if self.last_id:
            self.kwargs['min_pk'] = self.last_id
        self.kwargs['room'] = self.room
        return super().list(request, *args, **kwargs)
