# coding=UTF8
import os
from crypt import crypt
from random import choice
from string import ascii_letters, digits

from django.contrib.postgres.fields import ArrayField, HStoreField
from django.db import models

from apps.core.abstract_models import (
    CacheableAbstractModel,
    CreatedUpdatedAtAbstractModel,
    DescriptionAbstractModel,
    LiveAbstractModel,
    TrackChangesAbstractModel
)
from apps.core.backends.storage import DefaultStorage
from apps.core.decorators import cached
from apps.core.fields import LowercaseCharField, NullableJSONField
from apps.core.helpers import Cached, MetaIntEnum, generate_key, get_cur_loc_env
from apps.core.permissions import API_PERMISSIONS, FULL_PERMISSIONS
from apps.hosting.validators import VALID_DOMAIN_REGEX
from apps.instances.helpers import get_current_instance


def upload_hosting_file_to(instance, filename):
    _, ext = os.path.splitext(filename)
    return '{instance_prefix}/{hosting_id}h/{filename}{ext}'.format(
        instance_prefix=get_current_instance().get_storage_prefix(),
        hosting_id=instance.hosting_id,
        filename=generate_key(),
        ext=ext.lower()[:16]  # extensions longer than 16 would be kinda strange
    )


class Hosting(LiveAbstractModel, DescriptionAbstractModel,
              CacheableAbstractModel, CreatedUpdatedAtAbstractModel,
              TrackChangesAbstractModel):
    PERMISSION_CONFIG = {
        'admin': {
            'full': FULL_PERMISSIONS,
            'write': {API_PERMISSIONS.READ},
            'read': {API_PERMISSIONS.READ},
        }
    }
    UPDATE_LOCK_KEY_TEMPLATE = 'lock:hosting:update:{instance.id}'

    class SSL_STATUSES(MetaIntEnum):
        CHECKING = -1, 'checking'
        OFF = 0, 'off'
        ON = 1, 'on'
        INVALID_DOMAIN = 2, 'invalid_domain'
        CNAME_NOT_SET = 3, 'cname_not_set'
        WRONG_CNAME = 4, 'wrong_cname'
        UNKNOWN = 5, 'unknown'

    name = LowercaseCharField(max_length=253)
    domains = ArrayField(base_field=models.CharField(max_length=253), default=[])
    is_active = models.BooleanField(default=True)
    is_default = models.BooleanField(default=False)
    ssl_status = models.SmallIntegerField(choices=SSL_STATUSES.as_choices(),
                                          default=SSL_STATUSES.OFF.value)
    config = NullableJSONField(default={})
    socket = models.ForeignKey('sockets.Socket', blank=True, null=True, default=None, on_delete=models.CASCADE)
    auth = HStoreField(default={})

    _storage = None

    class Meta:
        ordering = ('id',)
        unique_together = ('name', '_is_live')
        verbose_name = 'Hosting'

    def __str__(self):
        return 'Hosting[id=%s, name=%s]' % (self.id, self.name)

    @classmethod
    def get_storage(cls):
        if cls._storage is None:
            cls._storage = DefaultStorage.create_storage(
                bucket_name=get_cur_loc_env('STORAGE_HOSTING_BUCKET'),
                storage_url=get_cur_loc_env('STORAGE_HOSTING_BUCKET_URL'),
            )
        return cls._storage

    @classmethod
    def get_instance_lock_key(cls, instance):
        return cls.UPDATE_LOCK_KEY_TEMPLATE.format(instance=instance)

    @staticmethod
    @cached()
    def is_hosting_empty(hosting_id):
        return not HostingFile.objects.filter(hosting=hosting_id).exists()

    @classmethod
    def cnames_generator(cls, domains):
        return (d for d in domains if VALID_DOMAIN_REGEX.match(d))

    @classmethod
    def find_cname(cls, domains):
        return next(cls.cnames_generator(domains), None)

    def get_cname(self):
        return Hosting.find_cname(self.domains)

    @property
    def is_empty(self):
        return Hosting.is_hosting_empty(self.id)

    @property
    def is_locked(self):
        return self.ssl_status == Hosting.SSL_STATUSES.CHECKING

    @property
    def is_browser_router_enabled(self):
        return self.config.get('browser_router', False)

    @classmethod
    def encrypt_passwd(cls, passwd):
        def salt():
            symbols = ascii_letters + digits
            return choice(symbols) + choice(symbols)
        return 'crypt:{}'.format(crypt(passwd, salt()))

    def check_auth(self, uname, passwd):
        if uname in self.auth:
            _, encrypted_passwd = self.auth[uname].split(':', 1)
            return crypt(passwd, encrypted_passwd) == encrypted_passwd
        return False


class HostingFile(LiveAbstractModel, CacheableAbstractModel, CreatedUpdatedAtAbstractModel, TrackChangesAbstractModel):
    PERMISSION_CONFIG = {
        'admin': {
            'full': FULL_PERMISSIONS,
            'write': {API_PERMISSIONS.READ},
            'read': {API_PERMISSIONS.READ},
        }
    }

    path = models.TextField(max_length=300)
    level = models.IntegerField(default=0)
    size = models.IntegerField()
    checksum = models.CharField(max_length=32, null=True)
    file_object = models.FileField(upload_to=upload_hosting_file_to, storage=Hosting.get_storage())
    hosting = models.ForeignKey('Hosting', on_delete=models.CASCADE)

    class Meta:
        ordering = ('id',)
        verbose_name = 'HostingFile'
        unique_together = ('hosting', 'path', '_is_live')

    def __str__(self):
        return 'HostingFile[id=%s, path=%s]' % (self.id, self.path)

    @classmethod
    def get_file_cached(cls, hosting_id, path):
        def _get_file():
            try:
                return cls.objects.filter(path=path, hosting=hosting_id).get()
            except cls.DoesNotExist:
                return 'DoesNotExist'

        return Cached(_get_file,
                      key='Hosting.GetFile',
                      version_key='i=%d;h=%d;p=%s' % (get_current_instance().id, hosting_id, path))

    @classmethod
    def get_file(cls, hosting, path):
        ret = cls.get_file_cached(hosting.id, path).get()
        if isinstance(ret, str):
            raise cls.DoesNotExist
        return ret

    @classmethod
    def invalidate_file(cls, hosting_id, path):
        cls.get_file_cached(hosting_id=hosting_id, path=path).invalidate()
