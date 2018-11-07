# coding=UTF8
import re

from django.core.validators import RegexValidator
from rest_framework import serializers
from rest_framework.serializers import ModelSerializer
from rest_framework.validators import UniqueValidator

from apps.core.field_serializers import JSONField
from apps.core.fields import LowercaseCharField
from apps.core.mixins.serializers import DynamicFieldsMixin, HyperlinkedMixin, ProcessReadOnlyMixin, RevalidateMixin
from apps.core.validators import DjangoValidator, validate_render_template_context, validate_template_context
from apps.response_templates.models import ResponseTemplate
from apps.response_templates.validators import Jinja2TemplateValidator


class ResponseTemplateSerializer(DynamicFieldsMixin, RevalidateMixin, HyperlinkedMixin, ModelSerializer):
    hyperlinks = (
        ('self', 'response-templates-detail', (
            'instance.name',
            'name',
        )),
        ('rename', 'response-templates-rename', (
            'instance.name',
            'name',
        )),
    )

    name = LowercaseCharField(validators=[
        UniqueValidator(queryset=ResponseTemplate.objects.all()),
        DjangoValidator()
    ])
    context = JSONField(default={}, validators=[validate_template_context])
    content = serializers.CharField(validators=[Jinja2TemplateValidator()])
    content_type = serializers.CharField(validators=[RegexValidator(
        regex=re.compile(r'^([a-z]+)\/([a-z0-9+-\.]+)*$', re.IGNORECASE),
        message='Not a valid content_type.')],
    )

    class Meta:
        fields = ('name', 'content', 'content_type', 'context', 'description')
        model = ResponseTemplate


class ResponseTemplateDetailSerializerMixin(ProcessReadOnlyMixin):
    additional_read_only_fields = ('name',)


class ResponseTemplateDetailSerializer(ResponseTemplateDetailSerializerMixin, ResponseTemplateSerializer):
    additional_read_only_fields = ('name',)


class RenderSerializer(serializers.Serializer):
    # on render endpoint allow to override restricted keys;
    context = JSONField(default={}, validators=[validate_render_template_context])
