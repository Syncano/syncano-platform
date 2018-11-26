# coding=UTF8
import re

from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.core.validators import RegexValidator
from django.db import connections, models, transaction
from jsonfield import JSONField

from apps.apikeys.models import ApiKey
from apps.core.abstract_models import (
    CacheableAbstractModel,
    DescriptionAbstractModel,
    LiveAbstractModel,
    MetadataAbstractModel,
    TrackChangesAbstractModel
)
from apps.core.fields import NullableJSONField, StrippedSlugField
from apps.core.helpers import MetaIntEnum, ReentrantLock, redis
from apps.core.permissions import API_PERMISSIONS
from apps.core.validators import NotInValidator
from apps.instances.contextmanagers import instance_context

from .helpers import create_schema, get_new_instance_db

Admin = settings.AUTH_USER_MODEL

INSTANCE_PROTECTED_NAMES = {'devcenter', 'support', 'sentry', 'admin', 'platform', 'redirect', 'media', 'signup',
                            'login', 'instance_subdomain', 'my_instance', 'instance_subdomain',
                            'myinstance', 'panel', 'account', 'noinstance', 'public', 'template1', 'status'}


class Instance(DescriptionAbstractModel, MetadataAbstractModel, CacheableAbstractModel, TrackChangesAbstractModel,
               LiveAbstractModel):

    PERMISSION_CONFIG = {'api_key': {API_PERMISSIONS.READ}}

    LOCK_KEY_TEMPLATE = 'lock:instance:{instance_pk}'
    LOCK_TIMEOUT = 120

    name = StrippedSlugField(max_length=64,
                             validators=[NotInValidator(values=INSTANCE_PROTECTED_NAMES),
                                         RegexValidator(regex=re.compile(r'--'),
                                                        message='Double hyphens are reserved.',
                                                        inverse_match=True)
                                         ],
                             allow_underscore=False)
    owner = models.ForeignKey(Admin, related_name='own_instances', on_delete=models.CASCADE)
    schema_name = models.CharField(max_length=63, null=True)
    version = models.IntegerField(default=1)
    location = models.TextField(default=settings.LOCATION, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    database = models.CharField(max_length=128, default=None, null=True)
    storage_prefix = models.CharField(max_length=64, null=True, default=None)
    config = JSONField(default={}, blank=True)

    klasses_acl = NullableJSONField(default=settings.DEFAULT_ENDPOINT_ACL)
    channels_acl = NullableJSONField(default=settings.DEFAULT_ENDPOINT_ACL)
    script_endpoints_acl = NullableJSONField(default=settings.DEFAULT_SCRIPT_ENDPOINT_ACL)
    groups_acl = NullableJSONField(default=settings.DEFAULT_ENDPOINT_ACL)

    domains = ArrayField(base_field=models.CharField(max_length=253), default=[])

    class Meta:
        ordering = ('id',)
        unique_together = ('name', '_is_live')

    def __str__(self):
        return 'Instance[id=%s, name=%s]' % (self.id, self.name)

    def save(self, *args, **kwargs):
        # Check if new
        sync_schema = kwargs.pop('sync_schema', True)
        if self.id is None:
            super().save(*args, **kwargs)
            # if user provided schema_name before initial save it is treated as
            # format string with self keyword argument
            if not self.schema_name:
                self.schema_name = '{self.id}_{self.name}'
            self.schema_name = self.schema_name.format(self=self)[:63]
            kwargs['force_insert'] = False
            db = get_new_instance_db(self)

            super().save(*args, **kwargs)

            with transaction.atomic(db):
                create_schema(connections[db], schema_name=self.schema_name, sync_schema=sync_schema)
            self.owner.add_to_instance(self)
        else:
            super().save(*args, **kwargs)

    def create_apikey(self, ignore_acl=False, allow_user_create=False,
                      allow_group_create=False, allow_anonymous_read=False):
        apikey = ApiKey.objects.create(
            ignore_acl=ignore_acl,
            allow_user_create=allow_user_create,
            allow_group_create=allow_group_create,
            allow_anonymous_read=allow_anonymous_read,
            instance=self)
        return apikey

    def get_storage_prefix(self):
        return self.storage_prefix or str(self.id)

    @classmethod
    def lock(cls, instance_pk):
        return redis.lock(cls.LOCK_KEY_TEMPLATE.format(instance_pk=instance_pk),
                          lock_class=ReentrantLock,
                          timeout=cls.LOCK_TIMEOUT, sleep=0.01)


class InstanceIndicator(TrackChangesAbstractModel):

    class TYPES(MetaIntEnum):
        SCHEDULES_COUNT = 0, 'schedules_count'
        STORAGE_SIZE = 1, 'storage_size'
        APNS_DEVICES_COUNT = 2, 'apns_devices'

    instance = models.ForeignKey(Instance, related_name='indicators', on_delete=models.CASCADE)
    type = models.SmallIntegerField(choices=TYPES.as_choices())
    value = models.BigIntegerField(default=0)

    class Meta:
        ordering = ('id', )
        unique_together = ('instance', 'type')
        index_together = ('type', 'value')

    @classmethod
    def refresh(cls, instance, storage_size=None):
        with instance_context(instance):
            from apps.codeboxes.models import CodeBoxSchedule
            from apps.push_notifications.models import APNSDevice

            cls.objects.filter(
                type=InstanceIndicator.TYPES.SCHEDULES_COUNT, instance=instance,
            ).update(value=CodeBoxSchedule.objects.count())

            InstanceIndicator.objects.filter(
                type=InstanceIndicator.TYPES.APNS_DEVICES_COUNT, instance=instance,
            ).update(value=APNSDevice.objects.filter(is_active=True).count())

            if storage_size:
                InstanceIndicator.objects.filter(
                    type=InstanceIndicator.TYPES.STORAGE_SIZE, instance=instance,
                ).update(value=storage_size)

    def __str__(self):
        return 'InstanceIndicator[id=%s, instance=%s, type=%s, value=%s]' % (
            self.id, self.instance.name, self.TYPES(self.type), self.value)
