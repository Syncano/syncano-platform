# coding=UTF8
from rest_condition import Or
from rest_framework.generics import get_object_or_404

from apps.admins.permissions import AdminHasPermissions
from apps.apikeys.permissions import ApiKeyHasPermissions
from apps.billing.permissions import OwnerInGoodStanding
from apps.core.decorators import force_atomic
from apps.core.mixins.views import GenericEndpointViewSetMixin
from apps.high_level.permissions import AllowEndpointAction
from apps.high_level.v1 import views as v1_views
from apps.high_level.v2.serializers import DataObjectHighLevelApiDetailSerializer, DataObjectHighLevelApiSerializer


class DataObjectHighLevelApiViewSet(GenericEndpointViewSetMixin, v1_views.DataObjectHighLevelApiViewSetBase):
    serializer_class = DataObjectHighLevelApiSerializer
    serializer_detail_class = DataObjectHighLevelApiDetailSerializer
    permission_classes = (
        Or(AdminHasPermissions, ApiKeyHasPermissions, AllowEndpointAction),
        OwnerInGoodStanding,
    )

    def endpoint_get(self, request, *args, **kwargs):
        return self.run_view(request, *args, **kwargs)

    @force_atomic(False)
    def endpoint_post(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        lookup_url_kwarg = self.lookup_url_kwarg or self.lookup_field
        filter_kwargs = {self.lookup_field: self.kwargs[lookup_url_kwarg]}
        self.object = get_object_or_404(queryset, **filter_kwargs)

        return self.run_data_api_view(request)
