from rest_framework import serializers

from apps.core.helpers import is_query_param_true
from apps.core.mixins.serializers import DynamicFieldsMixin
from apps.metrics.models import DayAggregate, HourAggregate


class ConvertToDateField(serializers.DateField):
    def to_representation(self, value):
        value = value.date()
        return super().to_representation(value)


class HourAggregateSerializer(DynamicFieldsMixin,
                              serializers.ModelSerializer):
    instance = serializers.CharField(source='instance_name')
    hour = serializers.DateTimeField(source='timestamp')

    class Meta:
        model = HourAggregate
        fields = ('hour', 'source', 'instance', 'value',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if 'request' in self.context and is_query_param_true(self.context['request'], 'total'):
            self.fields.pop('instance')


class DayAggregateSerializer(HourAggregateSerializer):
    instance = serializers.CharField(source='instance_name')
    date = ConvertToDateField(source='timestamp')

    class Meta:
        model = DayAggregate
        fields = ('date', 'source', 'instance', 'value',)
