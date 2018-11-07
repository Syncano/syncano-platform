# coding=UTF8
from apps.webhooks.v1 import views as v1_views
from apps.webhooks.v1_1.serializers import WebhookDetailSerializer, WebhookSerializer


class WebhookViewSet(v1_views.WebhookViewSet):
    serializer_class = WebhookSerializer
    serializer_detail_class = WebhookDetailSerializer
