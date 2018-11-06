from rest_condition import Or
from rest_framework import status, viewsets
from rest_framework.decorators import detail_route
from rest_framework.response import Response
from rest_framework.serializers import Serializer

from apps.admins.permissions import AdminHasPermissions
from apps.apikeys.models import ApiKey
from apps.apikeys.permissions import ApiKeyHasPermissions
from apps.billing.permissions import OwnerInGoodStanding
from apps.core.mixins.views import AtomicMixin
from apps.instances.mixins import InstanceBasedMixin

from .serializers import ApiKeySerializer


class ApiKeyViewSet(AtomicMixin,
                    InstanceBasedMixin,
                    viewsets.ModelViewSet):
    """
    Manage API keys available for given instance.
    """
    model = ApiKey
    queryset = ApiKey.objects.all()
    serializer_class = ApiKeySerializer
    permission_classes = (
        Or(AdminHasPermissions, ApiKeyHasPermissions),
        OwnerInGoodStanding,
    )

    def get_queryset(self):
        base_query = super().get_queryset().filter(instance=self.request.instance)

        if self.request.auth:
            return base_query.filter(pk=self.request.auth.id)
        return base_query

    @detail_route(methods=['post'], serializer_class=Serializer)
    def reset_key(self, request, *args, **kwargs):
        user = self.get_object()
        user.reset()

        return Response(status=status.HTTP_200_OK,
                        data=ApiKeySerializer(user,
                                              context=self.get_serializer_context()).data)
