# coding=UTF8
from apps.core.mixins.serializers import AclMixin

from ..v1 import serializers as v1_serializers


class KlassSerializer(AclMixin, v1_serializers.KlassSerializer):
    hyperlinks = (
        ('self', 'klass-detail', (
            'instance.name',
            'name',
        )),
        ('objects', 'dataobject-list', (
            'instance.name',
            'name',
        )),
        ('endpoint-acl', 'dataobject-acl', (
            'instance.name', 'name',
        ))
    )

    class Meta(v1_serializers.KlassSerializer.Meta):
        fields = ('name', 'description', 'schema', 'status',
                  'created_at', 'updated_at', 'objects_count', 'revision',
                  'acl', 'metadata')


class KlassDetailSerializer(v1_serializers.KlassDetailMixin, KlassSerializer):
    pass


class DataObjectSerializer(AclMixin, v1_serializers.DataObjectSerializer):
    hyperlinks = (
        ('self', 'dataobject-detail', (
            'instance.name',
            '_klass.name',
            'id',
        )),
        ('channel', 'channel-detail', ('instance.name', 'channel.name',)),
    )

    class Meta(v1_serializers.DataObjectSerializer.Meta):
        fields = ('id', 'created_at', 'updated_at', 'revision', 'acl', 'channel', 'channel_room')

    def to_internal_value(self, data):
        reverted_data = super(v1_serializers.DataObjectSerializer, self).to_internal_value(data)
        if reverted_data is None:
            return reverted_data

        if 'view' in self.context:
            reverted_data['_klass'] = self.context['view'].klass
        return reverted_data


class DataObjectDetailSerializer(v1_serializers.DataObjectDetailMixin, DataObjectSerializer):
    pass
