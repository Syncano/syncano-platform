# coding=UTF8
from django.http import Http404
from rest_condition import And, Or
from rest_framework import generics, permissions
from rest_framework.reverse import reverse

from apps.apikeys.permissions import ApiKeyHasPermissions
from apps.billing.permissions import OwnerInGoodStanding
from apps.core.exceptions import PermissionDenied
from apps.core.views import LinksView
from apps.instances.mixins import InstanceBasedMixin
from apps.instances.models import Instance
from apps.instances.permissions import ProtectInstanceAccess

from .serializers import InstanceConfigSerializer


class TopSnippetsLinkView(InstanceBasedMixin, LinksView):
    def generate_links(self):
        return {
            'scripts': reverse('codebox-list', args=(self.request.instance.name,), request=self.request),
            'templates': reverse('response-templates-list', args=(self.request.instance.name,), request=self.request),
            'config': reverse('instance-config', args=(self.request.instance.name,), request=self.request),
        }


class InstanceConfigView(InstanceBasedMixin, generics.RetrieveAPIView,
                         generics.UpdateAPIView):

    serializer_class = InstanceConfigSerializer
    model = Instance
    queryset = Instance.objects.all()
    permission_classes = (
        Or(
            And(permissions.IsAuthenticated, ProtectInstanceAccess),
            ApiKeyHasPermissions
        ),
        OwnerInGoodStanding,
    )

    def get_queryset(self):
        base_query = super().get_queryset()

        if self.request.user.is_authenticated:
            return base_query.filter(admin_roles__admin=self.request.user)
        elif self.request.auth:
            return base_query.filter(pk=self.request.auth.instance_id)
        raise PermissionDenied()

    def get_object(self):
        try:
            obj = self.get_queryset().get(pk=self.request.instance.pk)
        except Instance.DoesNotExist:
            raise Http404
        self.check_object_permissions(self.request, obj)
        return obj
