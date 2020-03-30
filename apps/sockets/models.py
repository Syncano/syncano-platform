# coding=UTF8
import os
import re
from hashlib import md5

from django.conf import settings
from django.core.files.storage import default_storage
from django.core.validators import RegexValidator
from django.db import models
from django.utils.crypto import get_random_string
from django.utils.text import slugify
from jsonfield import JSONField

from apps.core.abstract_models import (
    CacheableAbstractModel,
    CreatedUpdatedAtAbstractModel,
    DescriptionAbstractModel,
    LiveAbstractModel,
    MetadataAbstractModel,
    SimpleAclAbstractModel,
    TrackChangesAbstractModel,
    UniqueKeyAbstractModel
)
from apps.core.fields import NullableJSONField, StrippedSlugField
from apps.core.helpers import MetaEnum, MetaIntEnum, generate_key
from apps.core.permissions import API_PERMISSIONS, FULL_PERMISSIONS, Permission
from apps.core.validators import NotInValidator
from apps.instances.helpers import get_current_instance
from apps.webhooks.models import WebhookTrace

DISALLOWED_SOCKET_NAMES = {'install'}
DISALLOWED_SOCKET_SUFFIXES = {'history', 'traces'}


def upload_custom_socket_file_to(instance, filename):
    _, ext = os.path.splitext(filename)
    return '{instance_prefix}/sockets/{filename}{ext}'.format(
        instance_prefix=get_current_instance().get_storage_prefix(),
        filename=generate_key(),
        ext=ext.lower()[:16]  # extensions longer than 16 would be kinda strange
    )


def upload_custom_socketenvironment_file_to(instance, filename):
    _, ext = os.path.splitext(filename)
    return '{instance_prefix}/env/{filename}{ext}'.format(
        instance_prefix=get_current_instance().get_storage_prefix(),
        filename=generate_key(),
        ext=ext.lower()[:16]  # extensions longer than 16 would be kinda strange
    )


class Socket(TrackChangesAbstractModel, DescriptionAbstractModel, CreatedUpdatedAtAbstractModel, MetadataAbstractModel,
             LiveAbstractModel, UniqueKeyAbstractModel, CacheableAbstractModel):
    KEY_FIELD_KWARGS = {}
    PERMISSION_CONFIG = {
        'admin': {
            'write': FULL_PERMISSIONS,
            'read': {API_PERMISSIONS.READ},
        }
    }
    # Always recheck socket if any of these fields is modified
    RECHECK_FIELDS = {'config'}

    class STATUSES(MetaIntEnum):
        PROCESSING = -2, 'processing'
        ERROR = -1, 'error'
        CHECKING = 0, 'checking'
        OK = 1, 'ok'
        PROMPT = 2, 'prompt'

    class INSTALL_FLAGS(MetaEnum):
        CLASS_NODELETE = 'class_nodelete'

    name = StrippedSlugField(max_length=64,
                             validators=[NotInValidator(values=DISALLOWED_SOCKET_NAMES)],
                             allow_slash=True)
    status = models.SmallIntegerField(choices=STATUSES.as_choices(), default=STATUSES.PROCESSING.value)
    status_info = JSONField(default=None, null=True)
    install_url = models.URLField(default=None, null=True)
    config = JSONField(default={}, blank=True)
    install_config = NullableJSONField(default={})
    zip_file = models.FileField(blank=True, null=True, upload_to=upload_custom_socket_file_to)
    zip_file_list = JSONField(null=True)
    version = models.CharField(max_length=32, default=settings.SOCKETS_DEFAULT_VERSION)
    size = models.IntegerField(default=0)
    installed = NullableJSONField(default={})
    file_list = NullableJSONField(default={})
    environment = models.ForeignKey('sockets.SocketEnvironment', null=True, default=None, on_delete=models.SET_NULL)
    checksum = models.CharField(max_length=32, null=True)

    class Meta:
        ordering = ('id',)
        unique_together = (('name', '_is_live'), ('key', '_is_live'))

    def __str__(self):
        return 'Socket[id=%s, name=%s]' % (
            self.pk,
            self.name,
        )

    @property
    def is_locked(self):
        return self.status in (self.STATUSES.CHECKING, self.STATUSES.PROCESSING)

    @property
    def is_new_format(self):
        return self.created_at.date() >= settings.CODEBOX_RELEASE or self.environment_id is not None

    def set_status(self, status, status_info=None):
        self.status = status
        if status_info and isinstance(status_info, str):
            status_info = {'error': status_info}
        self.status_info = status_info

    def update(self):
        self.zip_file = None
        self.set_status(Socket.STATUSES.PROCESSING)
        self.save(update_fields=('status', 'status_info', 'zip_file'))

    def get_storage_path(self, path=''):
        if path.startswith('<'):
            path = 'inline'
        return self.get_storage_path_for_key(self.key, path)

    def get_hash(self):
        return 'S:{}'.format(self.checksum)

    def update_hash(self):
        # Update checksum
        hash_md5 = md5()
        for _, f in sorted(self.file_list.items()):
            hash_md5.update(f['checksum'].encode())
        self.checksum = hash_md5.hexdigest()

    def get_files(self):
        script_files = {}
        for key, script_data in self.file_list.items():
            if key == settings.SOCKETS_YAML:
                continue

            file_url = default_storage.internal_url(script_data['file'])
            if file_url.startswith('/'):
                file_url = 'http://{}{}'.format(settings.API_HOST, file_url)
            script_files[file_url] = self.get_local_path(key)
        return script_files

    @classmethod
    def get_storage_path_for_key(cls, key, path=''):
        if path:
            file_root, file_ext = os.path.splitext(path)
            path = '{}_{}{}'.format(file_root, get_random_string(7), file_ext)
        return '{instance_prefix}/sockets/{socket_key}/{path}'.format(
            instance_prefix=get_current_instance().get_storage_prefix(),
            socket_key=key,
            path=path
        )

    @classmethod
    def get_local_path(cls, path):
        if path.startswith('<'):
            return slugify(path[1:-1])
        return path


class SocketEndpoint(SimpleAclAbstractModel, MetadataAbstractModel, CacheableAbstractModel):
    # v2 permission config
    GET_PERMISSION = Permission('GET', actions=('endpoint_get',))
    PUT_PERMISSION = Permission('PUT', actions=('endpoint_put',))
    PATCH_PERMISSION = Permission('PATCH', actions=('endpoint_patch',))
    POST_PERMISSION = Permission('POST', actions=('endpoint_post',))
    DELETE_PERMISSION = Permission('DELETE', actions=('endpoint_delete',))
    OBJECT_ACL_PERMISSIONS = (
        GET_PERMISSION,
        PUT_PERMISSION,
        PATCH_PERMISSION,
        POST_PERMISSION,
        DELETE_PERMISSION,
    )

    name = StrippedSlugField(max_length=256,
                             validators=[
                                 NotInValidator(values=DISALLOWED_SOCKET_NAMES),
                                 RegexValidator(regex=re.compile(r'/({})$'.format(
                                     '|'.join(sorted(DISALLOWED_SOCKET_SUFFIXES))
                                 )), inverse_match=True,
                                     message='Value cannot end with {}.'.format(', '.join(
                                         sorted(DISALLOWED_SOCKET_SUFFIXES)))
                                 )
                             ],
                             allow_slash=True,
                             allow_dots=True,
                             unique=True)
    socket = models.ForeignKey(Socket, on_delete=models.CASCADE)
    calls = JSONField()

    class Meta:
        ordering = ('id',)

    def __str__(self):
        return 'SocketEndpoint[id=%s, name=%s]' % (
            self.pk,
            self.name,
        )

    @classmethod
    def create_channel_room_name(cls, channel, request):
        context = request.query_params.dict()
        if request.auth_user:
            context['user'] = request.auth_user.username
        elif 'user' in context:
            del context['user']

        return channel.format(**context)


class SocketEndpointTrace(WebhookTrace):
    list_template_args = '{socket_endpoint.id}'


class SocketHandler(MetadataAbstractModel):
    PERMISSION_CONFIG = {
        'admin': {
            'write': FULL_PERMISSIONS,
            'read': {API_PERMISSIONS.READ},
        }
    }

    socket = models.ForeignKey(Socket, on_delete=models.CASCADE)
    handler_name = models.CharField(max_length=256)
    handler = JSONField(default={}, blank=True)

    class Meta:
        ordering = ('id',)
        index_together = ('socket', 'handler_name')

    def __str__(self):
        return 'SocketHandler[id=%s, handler_name=%s]' % (
            self.pk,
            self.handler_name,
        )


class SocketEnvironment(TrackChangesAbstractModel, DescriptionAbstractModel, CreatedUpdatedAtAbstractModel,
                        MetadataAbstractModel, LiveAbstractModel, CacheableAbstractModel):
    PERMISSION_CONFIG = {
        'admin': {
            'write': FULL_PERMISSIONS,
            'read': {API_PERMISSIONS.READ},
        }
    }

    class STATUSES(MetaIntEnum):
        PROCESSING = 0, 'processing'
        ERROR = -1, 'error'
        OK = 1, 'ok'

    name = StrippedSlugField(max_length=64)
    status = models.SmallIntegerField(choices=STATUSES.as_choices(), default=STATUSES.PROCESSING.value)
    status_info = JSONField(default=None, null=True)
    zip_file = models.FileField(blank=True, null=True, upload_to=upload_custom_socketenvironment_file_to)
    fs_file = models.FileField(blank=True, null=True, upload_to=upload_custom_socketenvironment_file_to)
    checksum = models.CharField(max_length=32, null=True)

    class Meta:
        ordering = ('id',)
        unique_together = ('name', '_is_live')

    def __str__(self):
        return 'SocketEnvironment[id=%s, name=%s]' % (
            self.pk,
            self.name,
        )

    @property
    def is_locked(self):
        return self.status in (self.STATUSES.PROCESSING,)

    @property
    def is_ready(self):
        return self.status == self.STATUSES.OK

    def set_status(self, status, status_info=None):
        self.status = status
        if status_info and isinstance(status_info, str):
            status_info = {'error': status_info}
        self.status_info = status_info

    def get_hash(self):
        return 'E:{}'.format(self.checksum)

    def get_url(self):
        url = default_storage.internal_url(str(self.fs_file))
        if url.startswith('/'):
            url = 'http://{}{}'.format(settings.API_HOST, url)
        return url
