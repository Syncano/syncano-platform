# coding=UTF8
import hashlib

import rapidjson as json
from django.conf import settings
from django.db import models

from apps.core.abstract_models import (
    AclAbstractModel,
    CacheableAbstractModel,
    DescriptionAbstractModel,
    LiveAbstractModel,
    TrackChangesAbstractModel
)
from apps.core.fields import DictionaryField, StrippedSlugField
from apps.core.helpers import Cached, MetaIntEnum, redis
from apps.core.permissions import API_PERMISSIONS, FULL_PERMISSIONS, Permission
from apps.instances.helpers import get_current_instance
from apps.redis_storage import fields as redis_fields
from apps.redis_storage.models import RedisModel


def create_room_key(template, channel_id, channel_room, **kwargs):
    key = template.format(instance_pk=get_current_instance().pk, channel_id=channel_id, **kwargs)
    if channel_room is not None:
        room = hashlib.md5(channel_room.encode()).hexdigest()
        key += ':{room}'.format(room=room)
    return key


class Channel(AclAbstractModel, DescriptionAbstractModel, CacheableAbstractModel,
              TrackChangesAbstractModel, LiveAbstractModel):
    DEFAULT_NAME = 'default'
    EVENTLOG_NAME = 'eventlog'

    PUBLISH_LOCK_KEY_TEMPLATE = 'lock:channel:publish:{instance_pk}:{channel_id}'
    STREAM_CHANNEL_TEMPLATE = 'stream:channel:{instance_pk}:{channel_id}'

    # v1 permission config
    PERMISSION_CONFIG = {
        'admin': {
            'write': FULL_PERMISSIONS,
            'read': {API_PERMISSIONS.READ},
        }
    }

    class PERMISSIONS(MetaIntEnum):
        NONE = 0, 'none'
        SUBSCRIBE = 1, 'subscribe'
        PUBLISH = 2, 'publish'

    # v2 permission config
    GET_PERMISSION = Permission('get', actions=('retrieve', 'publish', 'poll', 'subscribe',))
    ENDPOINT_ACL_PERMISSIONS = (
        GET_PERMISSION,
    ) + AclAbstractModel.ENDPOINT_ACL_PERMISSIONS[1:]

    SUBSCRIBE_PERMISSION = Permission('subscribe', actions=('poll', 'subscribe',))
    PUBLISH_PERMISSION = Permission('publish')
    CUSTOM_PUBLISH_PERMISSION = Permission('custom_publish', actions=('publish',))
    OBJECT_ACL_PERMISSIONS = AclAbstractModel.OBJECT_ACL_PERMISSIONS + (
        SUBSCRIBE_PERMISSION,
        PUBLISH_PERMISSION,
        CUSTOM_PUBLISH_PERMISSION,
    )

    class TYPES(MetaIntEnum):
        DEFAULT = 0, 'default'
        SEPARATE_ROOMS = 1, 'separate_rooms'

    schema = [
        # Defines if /channel/xx/publish/ should be possible, otherwise will only store Data Object's changes
        {
            'name': 'custom_publish',
            'class': 'BooleanField',
            'kwargs': {
                'default': False
            }
        }
    ]
    name = StrippedSlugField(max_length=64)
    type = models.SmallIntegerField(default=TYPES.DEFAULT, choices=TYPES.as_choices())
    options = DictionaryField('options', schema=schema)

    # v1 permissions fields
    group = models.ForeignKey('users.Group', null=True, blank=True, on_delete=models.CASCADE)
    group_permissions = models.SmallIntegerField(default=PERMISSIONS.NONE, choices=PERMISSIONS.as_choices(),
                                                 db_index=True)
    other_permissions = models.SmallIntegerField(default=PERMISSIONS.NONE, choices=PERMISSIONS.as_choices(),
                                                 db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('id',)
        unique_together = ('name', '_is_live')

    def __str__(self):
        return 'Channel[name=%s]' % self.name

    def get_publish_lock_key(self, room):
        return create_room_key(template=Channel.PUBLISH_LOCK_KEY_TEMPLATE, channel_id=self.id, channel_room=room)

    def get_stream_channel_name(self, room):
        return create_room_key(template=Channel.STREAM_CHANNEL_TEMPLATE, channel_id=self.id, channel_room=room)

    def create_change(self, room=None, **kwargs):
        from apps.channels.v1.serializers import ChangeSerializer

        lock_key = self.get_publish_lock_key(room)
        with redis.lock(lock_key, timeout=settings.LOCK_TIMEOUT, sleep=0.01):
            change = Change.create(channel=self, room=room, **kwargs)

            message = ChangeSerializer(change, excluded_fields=('links',)).data
            message = json.dumps(message)
            redis.publish(self.get_stream_channel_name(room), message)
            return change

    @classmethod
    def get_default(cls):
        return Cached(Channel, kwargs={'name': Channel.DEFAULT_NAME}).get()

    @classmethod
    def get_eventlog(cls):
        return Cached(Channel, kwargs={'name': Channel.EVENTLOG_NAME}).get()


class Change(RedisModel):
    PERMISSION_CONFIG = {
        'api_key': {API_PERMISSIONS.READ},
        'admin': {
            'write': FULL_PERMISSIONS,
            'read': {API_PERMISSIONS.READ},
        }
    }

    class ACTIONS(MetaIntEnum):
        CUSTOM = 0, 'custom'
        CREATE = 1, 'create'
        UPDATE = 2, 'update'
        DELETE = 3, 'delete'

    list_template_args = '{channel.id}:{room}'
    list_max_size = {Channel.EVENTLOG_NAME: 100, 'default': 1000}
    ttl = {Channel.EVENTLOG_NAME: settings.CODEBOX_TRACE_TTL, 'default': settings.CHANGES_TTL}
    trimmed_ttl = {Channel.EVENTLOG_NAME: settings.CODEBOX_TRACE_TRIMMED_TTL, 'default': settings.CHANGES_TRIMMED_TTL}
    tenant_model = True

    created_at = redis_fields.DatetimeField(auto_now_add=True)
    action = redis_fields.IntegerField(default=ACTIONS.CUSTOM)
    author = redis_fields.JSONField(default={})
    metadata = redis_fields.JSONField(default={})
    payload = redis_fields.JSONField(default={})

    def __str__(self):
        return 'Change[id=%d]' % (self.id,)

    @classmethod
    def get_list_key(cls, **kwargs):
        room = kwargs.get('room')
        if room and isinstance(room, str):
            room = room.lower()
        kwargs['room'] = room
        return super().get_list_key(**kwargs)

    @classmethod
    def _get_channel_value(cls, dict_field, channel_name):
        if channel_name in dict_field:
            return dict_field[channel_name]
        return dict_field['default']

    @classmethod
    def get_list_max_size(cls, **kwargs):
        return cls._get_channel_value(cls.list_max_size, kwargs['channel'].name)

    @classmethod
    def get_ttl(cls, **kwargs):
        return cls._get_channel_value(cls.ttl, kwargs['channel'].name)

    @classmethod
    def get_trimmed_ttl(cls, **kwargs):
        return cls._get_channel_value(cls.trimmed_ttl, kwargs['channel'].name)
