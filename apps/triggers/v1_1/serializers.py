# coding=UTF8
from apps.triggers.v1 import serializers as v1_serializers


class TriggerSerializer(v1_serializers.TriggerSerializer):
    hyperlinks = (
        ('self', 'trigger-detail', (
            'instance.name',
            'pk',
        )),
        ('script', 'codebox-detail', (
            'instance.name',
            'codebox.id',
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

    field_mappings = {'codebox': 'script',
                      'klass': 'class'}
