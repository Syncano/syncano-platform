# coding=UTF8
from django.db import models
from jsonfield import JSONField

from apps.core.abstract_models import DescriptionAbstractModel
from apps.core.fields import DictionaryField, StrippedSlugField
from apps.core.permissions import API_PERMISSIONS, FULL_PERMISSIONS


class HighLevelApiAbstractModel(DescriptionAbstractModel):
    name = StrippedSlugField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class DataObjectHighLevelApi(HighLevelApiAbstractModel):
    PERMISSION_CONFIG = {
        'api_key': {
            API_PERMISSIONS.READ
        },
        'admin': {
            'write': FULL_PERMISSIONS,
            'read': {API_PERMISSIONS.READ},
        }
    }

    query = JSONField(default={}, blank=True)
    schema = [
        {
            'name': 'fields',
            'class': 'CharField',
            'kwargs': {
                'blank': True,
                'max_length': 256,
            }
        },
        {
            'name': 'excluded_fields',
            'class': 'CharField',
            'kwargs': {
                'blank': True,
                'max_length': 256,
            }
        },
        {
            'name': 'order_by',
            'class': 'CharField',
            'kwargs': {
                'blank': True,
                'max_length': 50,
            }
        },
        {
            'name': 'page_size',
            'class': 'IntegerField',
            'kwargs': {
                'blank': True,
            }
        },
        {
            'name': 'expand',
            'class': 'CharField',
            'kwargs': {
                'blank': True,
                'max_length': 256,
            }
        },
    ]

    klass = models.ForeignKey('data.Klass', on_delete=models.CASCADE)
    options = DictionaryField('options', schema=schema)

    class Meta:
        ordering = ('id', )
        verbose_name = 'Data Endpoint'

    @classmethod
    def get_possible_fields(cls):
        if not hasattr(cls, '_possible_fields'):
            possible_fields = [field['name'] for field in DataObjectHighLevelApi.schema]
            possible_fields.append('query')
            cls._possible_fields = possible_fields
        return cls._possible_fields
