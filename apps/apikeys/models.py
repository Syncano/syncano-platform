# coding=UTF8
from django.db import models

from apps.core.abstract_models import (
    CacheableAbstractModel,
    DescriptionAbstractModel,
    LiveAbstractModel,
    TrackChangesAbstractModel,
    UniqueKeyAbstractModel
)
from apps.core.fields import DictionaryField
from apps.core.helpers import generate_key
from apps.core.permissions import API_PERMISSIONS, FULL_PERMISSIONS


class ApiKey(DescriptionAbstractModel, CacheableAbstractModel, LiveAbstractModel, TrackChangesAbstractModel,
             UniqueKeyAbstractModel):
    KEY_FIELD_KWARGS = {}
    PERMISSION_CONFIG = {
        'api_key': {API_PERMISSIONS.READ},
        'admin': {
            'full': FULL_PERMISSIONS,
        }
    }

    created_at = models.DateTimeField(auto_now_add=True)
    instance = models.ForeignKey('instances.Instance', on_delete=models.CASCADE)

    schema = [
        {
            'name': 'ignore_acl',
            'class': 'BooleanField',
            'kwargs': {
                'default': False
            }
        },
        {
            'name': 'allow_user_create',
            'class': 'BooleanField',
            'kwargs': {
                'default': False
            }
        },
        {
            'name': 'allow_anonymous_read',
            'class': 'BooleanField',
            'kwargs': {
                'default': False
            }
        },
        {
            'name': 'allow_group_create',
            'class': 'BooleanField',
            'kwargs': {
                'default': False
            }
        },
    ]

    options = DictionaryField('options', schema=schema)

    class Meta:
        ordering = ('id',)
        unique_together = ('key', '_is_live')

    def __str__(self):
        return 'ApiKey[id=%s]' % (self.id,)

    def generate_key(self):
        return generate_key(parity=False)
