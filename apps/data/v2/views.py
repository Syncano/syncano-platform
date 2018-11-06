# coding=UTF8
from rest_condition import And, Or
from rest_framework import permissions

from apps.admins.permissions import AdminHasPermissions
from apps.billing.permissions import OwnerInGoodStanding
from apps.channels.models import Channel
from apps.core.mixins.views import EndpointAclMixin
from apps.core.permissions import CheckAclPermission
from apps.data.exceptions import ChannelPublishNotAllowed
from apps.data.permissions import ProtectUserProfileKlass
from apps.data.v2.serializers import (
    DataObjectDetailSerializer,
    DataObjectSerializer,
    KlassDetailSerializer,
    KlassSerializer
)

from ..v1 import views as v1_views


class KlassViewSet(EndpointAclMixin, v1_views.KlassViewSet):
    serializer_class = KlassSerializer
    serializer_detail_class = KlassDetailSerializer

    permission_classes = (
        OwnerInGoodStanding,
        And(
            ProtectUserProfileKlass,
            Or(
                # Check admin permissions
                AdminHasPermissions,
                # Check API Key ACL
                CheckAclPermission,
            ),
        ),
    )

    endpoint_acl_object_field = 'klasses_acl'

    def get_queryset(self):
        base_query = super(v1_views.KlassViewSet, self).get_queryset().filter(visible=True).filter_acl(self.request)
        if self.request.method in permissions.SAFE_METHODS:
            return base_query.include_object_count()
        return base_query


class ObjectViewSet(EndpointAclMixin, v1_views.ObjectViewSet):
    serializer_class = DataObjectSerializer
    serializer_detail_class = DataObjectDetailSerializer
    permission_classes = (
        OwnerInGoodStanding,
        Or(
            # Check admin permissions
            AdminHasPermissions,
            # Check API Key ACL
            CheckAclPermission,
        ),
    )

    endpoint_acl_object_field = 'objects_acl'

    query_fields = {'id', 'created_at', 'updated_at', 'revision', 'channel', 'channel_room'}

    def get_endpoint_acl_object(self, request):
        return self.klass

    def get_queryset(self):
        base_query = super(v1_views.ObjectViewSet, self).get_queryset().select_related('channel')
        return base_query.filter_acl(self.request)

    def validate_klass(self, obj):
        return obj.visible

    def check_channel_permission(self, request, obj):
        if request.auth and not Channel.PUBLISH_PERMISSION.check_acl(request, obj.acl):
            raise ChannelPublishNotAllowed()
