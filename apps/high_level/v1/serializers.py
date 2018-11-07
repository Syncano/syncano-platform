# coding=UTF8
from rest_framework.serializers import SlugRelatedField
from rest_framework.settings import api_settings
from rest_framework.validators import UniqueValidator

from apps.core.field_serializers import JSONField, LowercaseCharField
from apps.core.mixins.serializers import (
    DynamicFieldsMixin,
    HyperlinkedMixin,
    ProcessReadOnlyMixin,
    RemapperMixin,
    RevalidateMixin
)
from apps.core.validators import DjangoValidator
from apps.data.models import Klass
from apps.data.v1.serializers import HStoreSerializer
from apps.data.validators import validate_query
from apps.high_level.models import DataObjectHighLevelApi
from apps.high_level.validators import data_field_list_validator


class DataObjectHighLevelApiSerializer(RevalidateMixin, DynamicFieldsMixin, RemapperMixin, HyperlinkedMixin,
                                       HStoreSerializer):
    hyperlinks = (
        ('self', 'hla-objects-detail', (
            'instance.name',
            'name',
        )),
        ('get', 'hla-objects-get', (
            'instance.name',
            'name',
        )),
        ('post', 'hla-objects-post', (
            'instance.name',
            'name',
        )),
        ('rename', 'hla-objects-rename', (
            'instance.name',
            'name',
        )),
    )

    name = LowercaseCharField(validators=[
        UniqueValidator(queryset=DataObjectHighLevelApi.objects.all()),
        DjangoValidator()
    ])
    query = JSONField(validators=[validate_query],
                      default={})
    klass = SlugRelatedField(slug_field='name', label='class', queryset=Klass.objects.all())
    field_mappings = {'klass': 'class'}

    class Meta:
        model = DataObjectHighLevelApi
        fields = ('name', 'description', 'klass', 'query', 'excluded_fields', 'order_by',
                  'page_size', 'expand')
        extra_kwargs = {
            'excluded_fields': {'validators': [data_field_list_validator]},
            'fields': {'validators': [data_field_list_validator]},
            'expand': {'validators': [data_field_list_validator]},
            'page_size': {'min_value': 0, 'max_value': api_settings.PAGE_SIZE},
        }


class DataObjectHighLevelApiDetailMixin(ProcessReadOnlyMixin):
    additional_read_only_fields = ('name',)


class DataObjectHighLevelApiDetailSerializer(DataObjectHighLevelApiDetailMixin, DataObjectHighLevelApiSerializer):
    pass
