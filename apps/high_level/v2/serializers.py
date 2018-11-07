# coding=UTF8
from rest_framework.relations import SlugRelatedField

from apps.data.models import Klass
from apps.high_level.v1 import serializers as v1_serializers


class DataObjectHighLevelApiSerializer(v1_serializers.DataObjectHighLevelApiSerializer):
    hyperlinks = (
        ('self', 'hla-objects-endpoint', (
            'instance.name',
            'name',
        )),
        ('edit', 'hla-objects-detail', (
            'instance.name',
            'name',
        )),
        ('rename', 'hla-objects-rename', (
            'instance.name',
            'name',
        )),
    )
    klass = SlugRelatedField(slug_field='name', label='class', queryset=Klass.objects.exclude(name='user_profile'))


class DataObjectHighLevelApiDetailSerializer(v1_serializers.DataObjectHighLevelApiDetailMixin,
                                             DataObjectHighLevelApiSerializer):
    pass
