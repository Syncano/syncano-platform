# coding=UTF8
from rest_framework import serializers
from rest_framework.compat import MaxLengthValidator
from rest_framework.serializers import ModelSerializer

from apps.codeboxes.v2.serializers import TraceDetailSerializer, TraceSerializer
from apps.core.field_serializers import JSONField
from apps.core.mixins.serializers import DynamicFieldsMixin, HyperlinkedMixin, RemapperMixin
from apps.core.validators import PayloadValidator
from apps.triggers.events import event_registry
from apps.triggers.models import Trigger
from apps.triggers.v1.serializers import TriggerTraceBaseSerializer
from apps.triggers.validators import SignalValidator


class TriggerSerializer(DynamicFieldsMixin, RemapperMixin, HyperlinkedMixin, ModelSerializer):
    hyperlinks = (
        ('self', 'trigger-detail', (
            'instance.name',
            'pk',
        )),
        ('script', 'codebox-detail', (
            'instance.name',
            'codebox.id',
        )),
        ('traces', 'trigger-trace-list', (
            'instance.name',
            'pk',
        )),
        ('socket', 'socket-detail', (
            'instance.name',
            'socket.name',
        )),
    )
    field_mappings = {'codebox': 'script'}

    class Meta:
        model = Trigger
        fields = ('id', 'label', 'description', 'created_at', 'updated_at', 'codebox',
                  'signals', 'event')
        extra_kwargs = {'signals': {'validators': [
            MaxLengthValidator(8, 'Ensure this value has at most %(limit_value)d elements (it has %(show_value)d).')]}}

    def validate(self, data):
        # First validate event
        if 'event' in data:
            event_data = data['event']
        else:
            event_data = self.instance.event

        event = event_registry.match(event_data)
        if event is None:
            raise serializers.ValidationError({'event': 'Event is required to have a valid source defined.'})

        try:
            event.validate()
        except serializers.ValidationError as ex:
            raise serializers.ValidationError({'event': ex.detail})

        # Signals validator based on event
        if 'signals' in data:
            signals_data = data['signals']
        else:
            signals_data = self.instance.signals

        try:
            data['signals'] = event.validate_signals(signals_data)
        except serializers.ValidationError as ex:
            raise serializers.ValidationError({'signals': ex.detail})

        return data


class TriggerTraceSerializer(TriggerTraceBaseSerializer, TraceSerializer):
    pass


class TriggerTraceDetailSerializer(TriggerTraceBaseSerializer, TraceDetailSerializer):
    pass


class TriggerEmitSerializer(serializers.Serializer):
    signal = serializers.CharField(max_length=128, validators=[SignalValidator()])
    payload = JSONField(validators=[PayloadValidator()], default={})
