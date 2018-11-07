# coding=UTF8
from django.conf import settings
from rest_framework import serializers
from rest_framework.serializers import ModelSerializer

from apps.codeboxes.field_serializers import JSONFieldWithCutoff, TruncatedCharField
from apps.codeboxes.helpers import create_crontab
from apps.codeboxes.models import CodeBox, CodeBoxSchedule
from apps.codeboxes.runtimes import RUNTIME_CHOICES
from apps.core.field_serializers import JSONField
from apps.core.mixins.serializers import CleanValidateMixin, DynamicFieldsMixin, HyperlinkedMixin
from apps.core.validators import DjangoValidator, PayloadValidator, validate_config

CODEBOX_RESULT_PLACEHOLDER = {'__error__': 'Result is too big to show in trace.'}


class CodeBoxSerializer(DynamicFieldsMixin, HyperlinkedMixin, ModelSerializer):
    hyperlinks = (
        ('self', 'codebox-detail', (
            'instance.name',
            'pk',
        )),
        ('runtimes', 'runtime-list', (
            'instance.name',
        )),
        ('run', 'codebox-run', (
            'instance.name',
            'pk',
        )),
        ('traces', 'codebox-trace-list', (
            'instance.name',
            'pk',
        )),
    )
    config = JSONField(validators=[validate_config],
                       default={})
    source = TruncatedCharField(cutoff=settings.CODEBOX_SOURCE_CUTOFF,
                                trim_whitespace=False,
                                max_length=settings.CODEBOX_SOURCE_SIZE_LIMIT,
                                default='',
                                allow_blank=True)
    runtime_name = serializers.ChoiceField(choices=RUNTIME_CHOICES)

    class Meta:
        model = CodeBox
        fields = ('id', 'runtime_name', 'source', 'created_at', 'updated_at', 'config', 'label', 'description')


class CodeBoxRunSerializer(serializers.Serializer):
    payload = JSONField(validators=[PayloadValidator()], default={})


class TraceSerializer(DynamicFieldsMixin, HyperlinkedMixin, serializers.Serializer):
    id = serializers.IntegerField()
    status = serializers.CharField()
    executed_at = serializers.DateTimeField()
    duration = serializers.IntegerField()
    result = JSONFieldWithCutoff(cutoff=settings.CODEBOX_RESULT_CUTOFF,
                                 placeholder=CODEBOX_RESULT_PLACEHOLDER,
                                 default={})


class TraceDetailSerializer(TraceSerializer):
    result = JSONField(default={})


class CodeBoxTraceBaseSerializer(serializers.Serializer):
    hyperlinks = (
        ('self', 'codebox-trace-detail', (
            'instance.name',
            'codebox.id',
            'id',
        )),
    )


class CodeBoxTraceSerializer(CodeBoxTraceBaseSerializer, TraceSerializer):
    pass


class CodeBoxTraceDetailSerializer(CodeBoxTraceBaseSerializer, TraceDetailSerializer):
    pass


class ScheduleTraceBaseSerializer(serializers.Serializer):
    hyperlinks = (
        ('self', 'schedule-trace-detail', (
            'instance.name',
            'schedule.id',
            'id',
        )),
    )


class ScheduleTraceSerializer(ScheduleTraceBaseSerializer, TraceSerializer):
    pass


class ScheduleTraceDetailSerializer(ScheduleTraceBaseSerializer, TraceDetailSerializer):
    pass


class CodeBoxScheduleSerializer(DynamicFieldsMixin, HyperlinkedMixin, CleanValidateMixin, ModelSerializer):
    hyperlinks = (
        ('self', 'codebox-schedule-detail', (
            'instance.name',
            'pk',
        )),
        ('traces', 'schedule-trace-list', (
            'instance.name',
            'pk',
        )),
        ('codebox', 'codebox-detail', (
            'instance.name',
            'codebox_id',
        )),
    )
    timezone = serializers.CharField(validators=[DjangoValidator()], default='UTC')

    class Meta:
        model = CodeBoxSchedule
        fields = ('id', 'label', 'description', 'created_at', 'interval_sec', 'crontab', 'scheduled_next', 'codebox',
                  'timezone',)
        extra_kwargs = {
            'scheduled_next': {'read_only': True},
            'interval_sec': {'min_value': settings.PERIODIC_SCHEDULE_MIN_INTERVAL, 'max_value': 86400},
        }

    def validate_crontab(self, value):
        if not value:
            return value

        crontab_parts = value.split()
        if len(crontab_parts) != 5:
            raise serializers.ValidationError('Crontab has to have 5 parts specified.')

        try:
            create_crontab(*crontab_parts)
        except ValueError as e:
            raise serializers.ValidationError('Not a valid crontab, %s' % e)

        return value
