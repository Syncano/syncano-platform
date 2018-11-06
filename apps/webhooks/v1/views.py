# coding=UTF8
import logging

from django.conf import settings
from rest_framework import generics, permissions, status, viewsets
from rest_framework.decorators import detail_route
from rest_framework.response import Response
from rest_framework.serializers import Serializer
from rest_framework_extensions.mixins import DetailSerializerMixin

from apps.admins.permissions import AdminHasPermissions
from apps.billing.permissions import OwnerInGoodStanding
from apps.codeboxes.exceptions import LegacyCodeBoxDisabled
from apps.codeboxes.v1.views import TraceViewSet
from apps.core.decorators import force_atomic
from apps.core.mixins.views import AtomicMixin, CacheableObjectMixin
from apps.instances.mixins import InstanceBasedMixin
from apps.instances.throttling import InstanceRateThrottle
from apps.webhooks.mixins import RunWebhookMixin
from apps.webhooks.models import Webhook, WebhookTrace
from apps.webhooks.permissions import ProtectScriptEndpointAccess
from apps.webhooks.v1.serializers import (
    WebhookDetailSerializer,
    WebhookSerializer,
    WebhookTraceDetailSerializer,
    WebhookTraceSerializer
)

try:
    # try to import uwsgi first as that module is not be available outside of uwsgi context (e.g. during tests)
    import uwsgi
except ImportError:
    uwsgi = None

logger = logging.getLogger(__name__)


class WebhookViewSet(CacheableObjectMixin,
                     AtomicMixin,
                     InstanceBasedMixin,
                     DetailSerializerMixin,
                     RunWebhookMixin,
                     viewsets.ModelViewSet):
    model = Webhook
    queryset = Webhook.objects.all()
    lookup_field = 'name'
    serializer_class = WebhookSerializer
    serializer_detail_class = WebhookDetailSerializer
    permission_classes = (
        AdminHasPermissions,
        OwnerInGoodStanding,
        ProtectScriptEndpointAccess,
    )

    @force_atomic(False)
    @detail_route(methods=['get', 'post'],
                  serializer_detail_class=Serializer,
                  request_limit=settings.CODEBOX_PAYLOAD_SIZE_LIMIT)
    def run(self, request, *args, **kwargs):
        if not settings.LEGACY_CODEBOX_ENABLED:
            raise LegacyCodeBoxDisabled()

        return self.run_view(request)

    @detail_route(methods=['post'], serializer_detail_class=Serializer)
    def reset_link(self, request, *args, **kwargs):
        webhook = self.get_object()
        # change public_link
        webhook.reset()

        return Response(status=status.HTTP_200_OK,
                        data=WebhookDetailSerializer(webhook,
                                                     context=self.get_serializer_context()).data)


class WebhookPublicView(InstanceBasedMixin,
                        RunWebhookMixin,
                        generics.GenericAPIView):
    permission_classes = (permissions.AllowAny,)
    throttle_classes = (InstanceRateThrottle, )
    authentication_classes = []
    lookup_field = 'public_link'
    model = Webhook
    queryset = Webhook.objects.filter(public=True)
    serializer_class = Serializer
    request_limit = settings.CODEBOX_PAYLOAD_SIZE_LIMIT

    def get(self, request, *args, **kwargs):
        return self.run_view(request)

    def post(self, request, *args, **kwargs):
        return self.run_view(request)


class WebhookTraceViewSet(DetailSerializerMixin, TraceViewSet):
    model = WebhookTrace
    serializer_class = WebhookTraceSerializer
    serializer_detail_class = WebhookTraceDetailSerializer
