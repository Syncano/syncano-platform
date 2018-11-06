# coding=UTF8
from apps.channels.v1 import serializers as v1_serializers
from apps.core.mixins.serializers import AclMixin


class ChannelSerializer(AclMixin, v1_serializers.ChannelSerializer):
    hyperlinks = (
        ('self', 'channel-detail', (
            'instance.name',
            'name',
        )),
        ('subscribe', 'channel-subscribe', ('instance.name', 'name',)),
        ('publish', 'channel-publish', ('instance.name', 'name',)),
        ('history', 'change-list', (
            'instance.name',
            'name',
        )),
    )

    class Meta(v1_serializers.ChannelSerializer.Meta):
        fields = ('name', 'description', 'type', 'created_at', 'updated_at', 'acl')


class ChannelDetailSerializer(v1_serializers.ChannelDetailSerializerMixin, ChannelSerializer):
    additional_read_only_fields = ('name', 'type',)
