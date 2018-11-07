# coding=UTF8
from rest_framework import serializers
from rest_framework.serializers import ModelSerializer, SlugRelatedField

from apps.codeboxes.v1.serializers import TraceDetailSerializer, TraceSerializer
from apps.core.mixins.serializers import DynamicFieldsMixin, HyperlinkedMixin, RemapperMixin
from apps.data.models import Klass
from apps.triggers.models import Trigger


class TriggerSerializer(DynamicFieldsMixin, RemapperMixin, HyperlinkedMixin, ModelSerializer):
    hyperlinks = (
        ('self', 'trigger-detail', (
            'instance.name',
            'pk',
        )),
        ('codebox', 'codebox-detail', (
            'instance.name',
            'codebox_id',
        )),
        ('class', 'klass-detail', (
            'instance.name',
            'klass.name',
        )),
        ('traces', 'trigger-trace-list', (
            'instance.name',
            'pk',
        )),
    )

    klass = SlugRelatedField(slug_field='name', label='class', queryset=Klass.objects.all())
    signal = serializers.ChoiceField(choices=['post_update', 'post_create', 'post_delete'])

    field_mappings = {'klass': 'class'}

    class Meta:
        model = Trigger
        fields = ('id', 'label', 'description', 'signal', 'klass', 'created_at', 'updated_at', 'codebox',)


class TriggerTraceBaseSerializer(serializers.Serializer):
    hyperlinks = (
        ('self', 'trigger-trace-detail', (
            'instance.name',
            'trigger.id',
            'id',
        )),
    )


class TriggerTraceSerializer(TriggerTraceBaseSerializer, TraceSerializer):
    pass


class TriggerTraceDetailSerializer(TriggerTraceBaseSerializer, TraceDetailSerializer):
    pass
