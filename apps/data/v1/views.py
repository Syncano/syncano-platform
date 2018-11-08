from django.conf import settings
from django.db import transaction
from rest_condition import And, Or
from rest_framework import permissions, viewsets
from rest_framework.response import Response
from rest_framework_extensions.mixins import DetailSerializerMixin

from apps.admins.permissions import AdminHasPermissions
from apps.apikeys.permissions import (
    ApiKeyHasPermissions,
    IsApiKeyAccess,
    IsApiKeyAllowingAnonymousRead,
    IsApiKeyIgnoringAcl
)
from apps.billing.models import AdminLimit
from apps.billing.permissions import OwnerInGoodStanding
from apps.channels.permissions import HasPublishPermission
from apps.core.decorators import sql_timeout
from apps.core.helpers import is_query_param_true
from apps.core.mixins.views import AtomicMixin, AutocompleteMixin, NestedViewSetMixin, SignalSenderModelMixin
from apps.core.pagination import OrderedPagination
from apps.data.exceptions import ChannelPublishNotAllowed, KlassCountExceeded
from apps.data.filters import QueryFilterBackend
from apps.data.mixins import ObjectSchemaProcessViewMixin
from apps.data.models import DataObject, Klass
from apps.data.permissions import (
    HasDataObjectPermission,
    HasKlassCreateObjectPermission,
    HasKlassReadPermission,
    ProtectUserProfileDataObject,
    ProtectUserProfileKlass
)
from apps.data.v1.serializers import (
    DataObjectDetailSerializer,
    DataObjectSerializer,
    KlassDetailSerializer,
    KlassSerializer
)
from apps.instances.mixins import InstanceBasedMixin
from apps.instances.models import Instance
from apps.users.permissions import HasUser


class KlassViewSet(AutocompleteMixin,
                   AtomicMixin,
                   InstanceBasedMixin,
                   DetailSerializerMixin,
                   viewsets.ModelViewSet):
    model = Klass
    queryset = Klass.objects.all()
    lookup_field = 'name'
    serializer_class = KlassSerializer
    serializer_detail_class = KlassDetailSerializer
    permission_classes = (
        ProtectUserProfileKlass,
        Or(AdminHasPermissions, ApiKeyHasPermissions),
        OwnerInGoodStanding,
    )

    def get_queryset(self):
        base_query = super().get_queryset()

        if self.request.auth and not self.request.auth.ignore_acl:
            if self.request.auth_user:
                group_perm_query = """
                   data_klass.other_permissions >= %s OR (
                       data_klass.group_id IS NOT NULL AND
                       data_klass.group_permissions >= %s AND
                       EXISTS (
                            SELECT 1
                            FROM users_membership
                            WHERE data_klass.group_id = users_membership.group_id
                            AND users_membership.user_id = %s
                        )
                    )
                """
                base_query = base_query.extra(where=[group_perm_query],
                                              params=(Klass.PERMISSIONS.READ,
                                                      Klass.PERMISSIONS.READ,
                                                      self.request.auth_user.id))
            else:
                base_query = base_query.filter(other_permissions__gte=Klass.PERMISSIONS.READ)

        if self.request.method in permissions.SAFE_METHODS:
            return base_query.include_object_count()

        return base_query

    def perform_create(self, serializer):
        # Lock on instance for the duration of transaction to avoid race conditions
        with transaction.atomic():
            Instance.objects.select_for_update().get(pk=self.request.instance.pk)
            klass_limit = AdminLimit.get_for_admin(self.request.instance.owner_id).get_classes_count()
            if Klass.objects.count() >= klass_limit:
                raise KlassCountExceeded(klass_limit)
            serializer.save()

    def perform_destroy(self, instance):
        instance.clean()
        super().perform_destroy(instance)


class ObjectViewSet(AtomicMixin,
                    InstanceBasedMixin,
                    NestedViewSetMixin,
                    ObjectSchemaProcessViewMixin,
                    DetailSerializerMixin,
                    SignalSenderModelMixin,
                    viewsets.ModelViewSet):
    model = DataObject
    queryset = DataObject.objects.all()
    serializer_class = DataObjectSerializer
    serializer_detail_class = DataObjectDetailSerializer
    permission_classes = (
        OwnerInGoodStanding,
        And(
            ProtectUserProfileDataObject,
            Or(
                # Check admin permissions first
                AdminHasPermissions,
                And(
                    # Otherwise when we're dealing with api key access
                    IsApiKeyAccess,
                    Or(
                        # Force access when ignoring acl
                        IsApiKeyIgnoringAcl,
                        # Force access when allow anonymous read
                        And(
                            IsApiKeyAllowingAnonymousRead,
                            HasKlassReadPermission
                        ),
                        And(
                            # Or if user is associated - check relevant klass and DO permissions
                            HasUser,
                            Or(
                                HasKlassCreateObjectPermission,
                                And(HasKlassReadPermission, HasDataObjectPermission)
                            ),
                        ),
                    ),
                ),
            ),
        ),
    )

    pagination_class = OrderedPagination
    paginate_query_params = ('query',)
    order_fields = {'id', 'created_at', 'updated_at'}

    filter_backends = (QueryFilterBackend,)
    query_fields = {'id', 'created_at', 'updated_at', 'revision', 'owner', 'group', 'channel', 'channel_room'}
    query_fields_extra = {
        'channel': {'lookup': 'channel__name'},
    }

    def get_queryset(self):
        base_query = super().get_queryset().select_related('channel')

        if self.request.auth and not self.request.auth.ignore_acl:
            if self.request.auth_user:
                user_id = self.request.auth_user.id
                group_perm_query = """
                   (
                       data_dataobject.owner_permissions >= %s AND
                       data_dataobject.owner_id = %s
                   ) OR
                   data_dataobject.other_permissions >= %s OR (
                       data_dataobject.group_id IS NOT NULL AND
                       data_dataobject.group_permissions >= %s AND
                       EXISTS (
                            SELECT 1
                            FROM users_membership
                            WHERE data_dataobject.group_id = users_membership.group_id
                            AND users_membership.user_id = %s
                        )
                    )
                """
                base_query = base_query.extra(where=[group_perm_query],
                                              params=(DataObject.PERMISSIONS.READ,
                                                      user_id,
                                                      DataObject.PERMISSIONS.READ,
                                                      DataObject.PERMISSIONS.READ,
                                                      user_id))
            else:
                base_query = base_query.filter(other_permissions__gte=DataObject.PERMISSIONS.READ)
        return base_query

    def get_paginated_response(self, data, objects_count=None):
        response = super().get_paginated_response(data)
        if objects_count is not None:
            response.data['objects_count'] = objects_count
        return response

    @sql_timeout(DataObject, settings.DATA_OBJECT_STATEMENT_TIMEOUT)
    def list(self, request, *args, **kwargs):
        """Get list of available objects"""
        queryset = self.filter_queryset(self.get_queryset())

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            objects_count = None
            if is_query_param_true(request, 'include_count'):
                objects_count = queryset.count_estimate()
            return self.get_paginated_response(serializer.data, objects_count=objects_count)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    def check_channel_permission(self, request, obj):
        # That's a little custom but as it is done in post_save and operate on an object
        # that is fetched later with a share lock (select for update).
        # It may feel even more custom and forced in permission_classes and would hold lock longer.
        if request.auth_user and not request.auth.ignore_acl:
            if not HasPublishPermission().has_object_permission(request, self, obj):
                raise ChannelPublishNotAllowed()
