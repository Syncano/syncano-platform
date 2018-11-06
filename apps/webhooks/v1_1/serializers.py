# coding=UTF8
from apps.core.mixins.serializers import RemapperMixin
from apps.webhooks.v1 import serializers as v1_serializers


class WebhookSerializer(RemapperMixin, v1_serializers.WebhookSerializer):
    hyperlinks = (
        ('self', 'webhook-detail', (
            'instance.name',
            'name',
        )),
        ('run', 'webhook-run', (
            'instance.name',
            'name',
        )),
        ('reset-link', 'webhook-reset-link', (
            'instance.name',
            'name',
        )),
        ('script', 'codebox-detail', (
            'instance.name',
            'codebox.id',
        )),
        ('public-link', 'webhook-public-run-with-name', (
            'instance.name',
            'public_link',
            'name'
        )),
        ('traces', 'webhook-trace-list', (
            'instance.name',
            'name',
        )),
    )

    field_mappings = {'codebox': 'script'}


class WebhookDetailSerializer(v1_serializers.WebhookDetailMixin, WebhookSerializer):
    pass
