# coding=UTF8
from django.http import HttpResponse
from rest_condition import Or
from rest_framework import status, viewsets
from rest_framework.decorators import detail_route
from rest_framework.response import Response
from rest_framework_extensions.mixins import DetailSerializerMixin

from apps.admins.permissions import AdminHasPermissions
from apps.apikeys.permissions import ApiKeyHasPermissions
from apps.billing.permissions import OwnerInGoodStanding
from apps.core.mixins.views import RenameNameViewSetMixin
from apps.instances.mixins import InstanceBasedMixin
from apps.response_templates.models import ResponseTemplate
from apps.response_templates.permissions import AllowApiKeyRenderAccess
from apps.response_templates.serializers import (
    RenderSerializer,
    ResponseTemplateDetailSerializer,
    ResponseTemplateSerializer
)


class ResponseTemplateViewSet(InstanceBasedMixin, DetailSerializerMixin, RenameNameViewSetMixin, viewsets.ModelViewSet):
    permission_classes = (
        Or(AdminHasPermissions, ApiKeyHasPermissions, AllowApiKeyRenderAccess),
        OwnerInGoodStanding,
    )
    model = ResponseTemplate
    queryset = ResponseTemplate.objects.all()
    lookup_field = 'name'
    serializer_class = ResponseTemplateSerializer
    serializer_detail_class = ResponseTemplateDetailSerializer

    @detail_route(methods=['post'], serializer_detail_class=RenderSerializer)
    def render(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            template = self.get_object()
            context = serializer.validated_data.get('context') or template.context
            return HttpResponse(template.render(request, context=context),
                                content_type='{0}; charset=utf-8'.format(template.content_type),
                                status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
