# coding=UTF8
from django.conf import settings
from rest_framework import serializers
from rest_framework.serializers import ModelSerializer
from rest_framework.validators import UniqueValidator

from apps.codeboxes.field_serializers import JSONFieldWithCutoff
from apps.codeboxes.v1.serializers import TraceDetailSerializer, TraceSerializer
from apps.core.field_serializers import JSONField, LowercaseCharField
from apps.core.mixins.serializers import DynamicFieldsMixin, HyperlinkedMixin, ProcessReadOnlyMixin, RevalidateMixin
from apps.core.validators import DjangoValidator, PayloadValidator
from apps.webhooks.models import Webhook

WEBHOOK_PAYLOAD_PLACEHOLDER = {'__error__': 'Payload is too big to show in trace.'}


class WebhookSerializer(RevalidateMixin, DynamicFieldsMixin, HyperlinkedMixin, ModelSerializer):
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
        ('codebox', 'codebox-detail', (
            'instance.name',
            'codebox_id',
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

    name = LowercaseCharField(validators=[
        UniqueValidator(queryset=Webhook.objects.all()),
        DjangoValidator()
    ])

    class Meta:
        model = Webhook
        fields = ('name', 'description', 'codebox', 'public_link', 'public',)
        extra_kwargs = {
            'public_link': {'read_only': True},
        }


class WebhookDetailMixin(ProcessReadOnlyMixin):
    additional_read_only_fields = ('name',)


class WebhookDetailSerializer(WebhookDetailMixin, WebhookSerializer):
    pass


class WebhookRunSerializer(serializers.Serializer):
    payload_validator = PayloadValidator()

    POST = JSONField(default={})
    GET = JSONField(default={})

    def validate(self, data):
        data = super().validate(data)
        # Call validators manually as we don't want to output validation error specific to a non user field
        self.payload_validator(data['POST'])
        return data


class WebhookTraceBaseSerializer(serializers.Serializer):
    hyperlinks = (
        ('self', 'webhook-trace-detail', (
            'instance.name',
            'webhook.name',
            'id',
        )),
    )

    meta = JSONField(default={})
    args = JSONFieldWithCutoff(cutoff=settings.CODEBOX_PAYLOAD_CUTOFF,
                               placeholder=WEBHOOK_PAYLOAD_PLACEHOLDER,
                               default={})


class WebhookTraceSerializer(WebhookTraceBaseSerializer, TraceSerializer):
    pass


class WebhookTraceDetailSerializer(WebhookTraceBaseSerializer, TraceDetailSerializer):
    args = JSONField(default={})
