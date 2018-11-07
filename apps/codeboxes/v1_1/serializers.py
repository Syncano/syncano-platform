# coding=UTF8
from apps.core.mixins.serializers import RemapperMixin

from ..v1.serializers import CodeBoxScheduleSerializer as _CodeBoxScheduleSerializer


class CodeBoxScheduleSerializer(RemapperMixin, _CodeBoxScheduleSerializer):
    hyperlinks = (
        ('self', 'codebox-schedule-detail', (
            'instance.name',
            'pk',
        )),
        ('traces', 'schedule-trace-list', (
            'instance.name',
            'pk',
        )),
        ('script', 'codebox-detail', (
            'instance.name',
            'codebox_id',
        )),
    )

    field_mappings = {'codebox': 'script'}
