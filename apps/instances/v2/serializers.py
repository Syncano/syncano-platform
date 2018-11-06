# coding=UTF8
from apps.instances.v1 import serializers as v1_serializers
from apps.instances.v1_1 import serializers as v1_1_serializers


class InstanceSerializer(v1_1_serializers.InstanceSerializer):
    hyperlinks = v1_1_serializers.InstanceSerializer.hyperlinks + (
        ('classes-acl', 'klass-acl', ('name',)),
        ('channels-acl', 'channel-acl', ('name',)),
        ('script-endpoints-acl', 'webhook-acl', ('name',)),
        ('groups-acl', 'group-acl', ('name',)),
        ('users-schema', 'user-schema', ('name',)),
        ('triggers-emit', 'trigger-emit', ('name',)),
        ('sockets', 'socket-list', ('name',)),
        ('sockets-install', 'socket-install', ('name',)),
        ('environments', 'socket-environment-list', ('name',)),
    )


class InstanceDetailSerializer(v1_serializers.InstanceDetailMixin, InstanceSerializer):
    pass
