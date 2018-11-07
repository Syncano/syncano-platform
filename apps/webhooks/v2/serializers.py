# coding=UTF8
from rest_framework import serializers

from apps.codeboxes.v2.serializers import TraceDetailSerializer, TraceSerializer
from apps.core.field_serializers import JSONField
from apps.core.mixins.serializers import AclMixin
from apps.webhooks.v1 import serializers as v1_serializers
from apps.webhooks.v1_1 import serializers as v1_1_serializers


class WebhookSerializer(AclMixin, v1_1_serializers.WebhookSerializer):
    hyperlinks = (
        ('self', 'webhook-endpoint', (
            'instance.name',
            'name',
        )),
        ('edit', 'webhook-detail', (
            'instance.name',
            'name',
        )),
        ('script', 'codebox-detail', (
            'instance.name',
            'codebox.id',
        )),
        ('traces', 'webhook-trace-list', (
            'instance.name',
            'name',
        )),
        ('socket', 'socket-detail', (
            'instance.name',
            'socket.name',
        )),
    )

    class Meta(v1_1_serializers.WebhookSerializer.Meta):
        fields = ('name', 'description', 'codebox', 'acl',)


class WebhookDetailSerializer(v1_serializers.WebhookDetailMixin, WebhookSerializer):
    pass


class WebhookTraceBaseSerializer(serializers.Serializer):
    hyperlinks = (
        ('self', 'webhook-trace-detail', (
            'instance.name',
            'webhook.name',
            'id',
        )),
    )

    meta = JSONField(default={})


class WebhookTraceSerializer(WebhookTraceBaseSerializer, TraceSerializer):
    pass


class WebhookTraceDetailSerializer(WebhookTraceBaseSerializer, TraceDetailSerializer):
    args = JSONField(default={})
