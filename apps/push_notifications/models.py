# coding=UTF8
from django.db import models
from jsonfield import JSONField

from apps.core.abstract_models import (
    CacheableAbstractModel,
    CreatedUpdatedAtAbstractModel,
    LabelAbstractModel,
    MetadataAbstractModel,
    TrackChangesAbstractModel
)
from apps.core.helpers import MetaIntEnum
from apps.core.permissions import API_PERMISSIONS, FULL_PERMISSIONS
from apps.users.models import User

from .fields import HexIntegerField


class GCMConfig(CacheableAbstractModel):
    PERMISSION_CONFIG = {
        'admin': {
            'write': FULL_PERMISSIONS,
            'read': {API_PERMISSIONS.READ},
        }
    }

    production_api_key = models.CharField(max_length=40, blank=True, null=True)
    development_api_key = models.CharField(max_length=40, blank=True, null=True)

    class Meta:
        verbose_name = 'GCM Config'

    def __str__(self):
        return 'GCMConfig[id=%s]' % self.id


class APNSConfig(CacheableAbstractModel):
    PERMISSION_CONFIG = {
        'admin': {
            'write': FULL_PERMISSIONS,
            'read': {API_PERMISSIONS.READ},
        }
    }

    production_certificate_name = models.CharField(max_length=200, blank=True, null=True)
    production_certificate = models.BinaryField(blank=True, null=True)
    production_bundle_identifier = models.CharField(max_length=200, blank=True, null=True)
    production_expiration_date = models.DateTimeField(blank=True, null=True)

    development_certificate_name = models.CharField(max_length=200, blank=True, null=True)
    development_certificate = models.BinaryField(blank=True, null=True)
    development_bundle_identifier = models.CharField(max_length=200, blank=True, null=True)
    development_expiration_date = models.DateTimeField(blank=True, null=True)

    class Meta:
        verbose_name = 'APNS Config'

    def __str__(self):
        return 'APNSConfig[id=%s]' % self.id


class Device(LabelAbstractModel, CreatedUpdatedAtAbstractModel, models.Model):
    PERMISSION_CONFIG = {
        'admin': {
            'write': FULL_PERMISSIONS,
            'read': {API_PERMISSIONS.READ},
        }
    }

    user = models.ForeignKey(User, blank=True, null=True, on_delete=models.CASCADE)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        abstract = True
        ordering = ('id', )


class GCMDevice(Device, MetadataAbstractModel):
    device_id = HexIntegerField(blank=True, null=True, db_index=True)
    registration_id = models.CharField(max_length=512, unique=True)

    class Meta(Device.Meta):
        verbose_name = 'GCM Device'


class APNSDevice(Device, TrackChangesAbstractModel, MetadataAbstractModel):
    device_id = models.UUIDField(blank=True, null=True, db_index=True)
    registration_id = models.CharField(max_length=64, unique=True)

    class Meta(Device.Meta):
        verbose_name = 'APNS Device'


class Message(CreatedUpdatedAtAbstractModel, models.Model):
    PERMISSION_CONFIG = {
        'admin': {
            'write': FULL_PERMISSIONS,
            'read': {API_PERMISSIONS.READ},
        }
    }

    class STATUSES(MetaIntEnum):
        SCHEDULED = 0, 'scheduled'
        ERROR = 1, 'error'
        PARTIALLY_DELIVERED = 2, 'partially_delivered'
        DELIVERED = 3, 'delivered'

    status = models.SmallIntegerField(choices=STATUSES.as_choices(), default=STATUSES.SCHEDULED)
    content = JSONField(default={})
    result = JSONField(default={})

    class Meta:
        ordering = ('id', )
        abstract = True


class GCMMessage(Message):

    class Meta(Message.Meta):
        verbose_name = 'GCM Message'


class APNSMessage(Message):

    class Meta(Message.Meta):
        verbose_name = 'APNS Message'
