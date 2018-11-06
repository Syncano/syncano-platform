# coding=UTF8
from rest_framework import serializers

from apps.codeboxes.v1 import serializers as v1_serializers
from apps.codeboxes.v1_1 import serializers as v1_1_serializers
from apps.core.field_serializers import JSONField
from apps.core.mixins.serializers import DynamicFieldsMixin, HyperlinkedMixin


class TraceSerializer(DynamicFieldsMixin, HyperlinkedMixin, serializers.Serializer):
    id = serializers.IntegerField()
    status = serializers.CharField()
    executed_at = serializers.DateTimeField()
    duration = serializers.IntegerField()


class TraceDetailSerializer(TraceSerializer):
    result = JSONField(default={})


class CodeBoxTraceSerializer(v1_serializers.CodeBoxTraceBaseSerializer, TraceSerializer):
    pass


class CodeBoxTraceDetailSerializer(v1_serializers.CodeBoxTraceBaseSerializer, TraceDetailSerializer):
    pass


class ScheduleTraceSerializer(v1_serializers.ScheduleTraceBaseSerializer, TraceSerializer):
    pass


class ScheduleTraceDetailSerializer(v1_serializers.ScheduleTraceBaseSerializer, TraceDetailSerializer):
    pass


class CodeBoxSerializer(v1_serializers.CodeBoxSerializer):
    hyperlinks = v1_serializers.CodeBoxSerializer.hyperlinks + (
        ('socket', 'socket-detail', (
            'instance.name',
            'socket.name',
        )),
    )


class CodeBoxScheduleSerializer(v1_1_serializers.CodeBoxScheduleSerializer):
    hyperlinks = v1_serializers.CodeBoxScheduleSerializer.hyperlinks + (
        ('socket', 'socket-detail', (
            'instance.name',
            'socket.name',
        )),
    )
