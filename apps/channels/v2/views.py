# coding=UTF8
from rest_condition import Or
from rest_framework.decorators import detail_route

from apps.admins.permissions import AdminHasPermissions
from apps.batch.decorators import disallow_batching
from apps.billing.permissions import OwnerInGoodStanding
from apps.channels.permissions import CheckChangeAclPermission, EnsureChannelRoom, ProtectBuiltinChannel
from apps.channels.throttling import ChannelPollRateThrottle
from apps.channels.v1 import views as v1_views
from apps.channels.v1.serializers import ChannelPublishSerializer, ChannelSubscribeSerializer
from apps.channels.v1.views import CHANNEL_PAYLOAD_LIMIT
from apps.channels.v2.serializers import ChannelDetailSerializer, ChannelSerializer
from apps.core.mixins.views import EndpointAclMixin
from apps.core.permissions import CheckAclPermission
from apps.core.throttling import AnonRateThrottle


class ChannelViewSet(EndpointAclMixin,
                     v1_views.ChannelViewSet):
    serializer_class = ChannelSerializer
    serializer_detail_class = ChannelDetailSerializer
    permission_classes = (
        Or(
            # Check admin permissions
            AdminHasPermissions,
            # Check API Key ACL
            CheckAclPermission,
        ),
        ProtectBuiltinChannel,
        OwnerInGoodStanding,
    )

    endpoint_acl_object_field = 'channels_acl'

    def get_queryset(self):
        base_query = super(v1_views.ChannelViewSet, self).get_queryset()
        return base_query.filter_acl(self.request)

    @disallow_batching
    @detail_route(methods=['get'],
                  serializer_detail_class=ChannelSubscribeSerializer,
                  throttle_classes=(AnonRateThrottle, ChannelPollRateThrottle,))
    def subscribe(self, request, *args, **kwargs):
        return super().poll(request, *args, **kwargs)

    @detail_route(methods=['post'],
                  serializer_detail_class=ChannelPublishSerializer,
                  request_limit=CHANNEL_PAYLOAD_LIMIT)
    def publish(self, request, *args, **kwargs):
        return super().publish(request, *args, **kwargs)


class ChangeViewSet(v1_views.ChangeViewSet):
    permission_classes = (
        Or(
            # Check admin permissions
            AdminHasPermissions,
            # Check API Key ACL
            CheckChangeAclPermission,
        ),
        EnsureChannelRoom,
        OwnerInGoodStanding,
    )
