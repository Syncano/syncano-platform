# coding=UTF8
from apps.instances.v1 import serializers as v1_serializers


class InstanceSerializer(v1_serializers.InstanceSerializer):
    hyperlinks = (
        ('self', 'instance-detail', ('name',)),
        ('admins', 'instance-admin-list', ('name',)),
        ('snippets', 'snippets', ('name',)),
        ('endpoints', 'endpoints', ('name',)),
        ('push_notification', 'push-notifications', ('name',)),
        ('classes', 'klass-list', ('name',)),
        ('invitations', 'invitation-list', ('name',)),
        ('api_keys', 'apikey-list', ('name',)),
        ('triggers', 'trigger-list', ('name',)),
        ('schedules', 'codebox-schedule-list', ('name',)),
        ('users', 'user-list', ('name',)),
        ('groups', 'group-list', ('name',)),
        ('channels', 'channel-list', ('name',)),
        ('batch', 'batch', ('name',)),
        ('rename', 'instance-rename', ('name',)),
        ('backups', 'instance_backups', ('name',)),
        ('restores', 'restores-list', ('name',)),
        ('hosting', 'hosting-list', ('name',)),
    )


class InstanceDetailSerializer(v1_serializers.InstanceDetailMixin, InstanceSerializer):
    pass
