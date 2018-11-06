# coding=UTF8
from django.conf import settings
from rest_condition import Or
from rest_framework import viewsets
from rest_framework_extensions.mixins import DetailSerializerMixin

from apps.admins.permissions import AdminHasPermissions
from apps.billing.permissions import OwnerInGoodStanding
from apps.core.mixins.views import (
    AtomicMixin,
    CacheableObjectMixin,
    EndpointAclMixin,
    EndpointViewSetMixin,
    RenameNameViewSetMixin
)
from apps.core.permissions import CheckAclPermission
from apps.instances.mixins import InstanceBasedMixin
from apps.webhooks.mixins import RunWebhookMixin
from apps.webhooks.models import Webhook
from apps.webhooks.permissions import ProtectScriptEndpointAccess
from apps.webhooks.v1 import views as v1_views
from apps.webhooks.v2.serializers import (
    WebhookDetailSerializer,
    WebhookSerializer,
    WebhookTraceDetailSerializer,
    WebhookTraceSerializer
)


class WebhookViewSet(EndpointAclMixin,
                     RenameNameViewSetMixin,
                     EndpointViewSetMixin,
                     CacheableObjectMixin,
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
        Or(
            # Check admin permissions
            AdminHasPermissions,
            # Check API Key ACL
            CheckAclPermission,
        ),
        OwnerInGoodStanding,
        ProtectScriptEndpointAccess,
    )

    endpoint_acl_object_field = 'script_endpoints_acl'
    request_limit = settings.CODEBOX_PAYLOAD_SIZE_LIMIT

    def get_queryset(self):
        return super().get_queryset().filter_acl(self.request).select_related('socket')

    def process_endpoint(self):
        return self.run_view(self.request)


class WebhookTraceViewSet(v1_views.WebhookTraceViewSet):
    list_deferred_fields = {'result', 'args'}
    serializer_class = WebhookTraceSerializer
    serializer_detail_class = WebhookTraceDetailSerializer
