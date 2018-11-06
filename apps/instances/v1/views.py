# coding=UTF8
from rest_condition import And, Or
from rest_framework import permissions, viewsets
from rest_framework_extensions.mixins import DetailSerializerMixin

from apps.admins.models import Admin
from apps.apikeys.permissions import ApiKeyHasPermissions
from apps.billing.models import AdminLimit
from apps.core.exceptions import PermissionDenied
from apps.core.mixins.views import AtomicMixin, AutocompleteMixin, RenameNameViewSetMixin
from apps.instances.exceptions import InstanceCountExceeded
from apps.instances.models import Instance
from apps.instances.permissions import InstanceAccessAdminInGoodStanding, InstanceLocationMatch, ProtectInstanceAccess
from apps.instances.v1.serializers import InstanceDetailSerializer, InstanceSerializer


class InstanceViewSet(AutocompleteMixin,
                      AtomicMixin,
                      DetailSerializerMixin,
                      RenameNameViewSetMixin,
                      viewsets.ModelViewSet):
    model = Instance
    queryset = Instance.objects.all()
    lookup_field = 'name'
    serializer_class = InstanceSerializer
    serializer_detail_class = InstanceDetailSerializer
    permission_classes = (
        Or(
            And(permissions.IsAuthenticated, ProtectInstanceAccess),
            ApiKeyHasPermissions
        ),
        InstanceAccessAdminInGoodStanding,
        InstanceLocationMatch,
    )

    def get_queryset(self):
        base_query = super().get_queryset().select_related('owner')

        if self.request.user.is_authenticated:
            return base_query.filter(admin_roles__admin=self.request.user).extra(
                select={'role': '"admins_admininstancerole"."role_id"'})
        elif self.request.auth:
            return base_query.filter(pk=self.request.auth.instance_id)
        raise PermissionDenied()

    def perform_create(self, serializer):
        # Lock on admin for the duration of transaction to avoid race conditions
        admin = Admin.objects.select_for_update().get(pk=self.request.user.id)
        instances_limit = AdminLimit.get_for_admin(self.request.user.id).get_instances_count()
        if Instance.objects.filter(owner=admin).count() >= instances_limit:
            raise InstanceCountExceeded(instances_limit)
        serializer.save()
