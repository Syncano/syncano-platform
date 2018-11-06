# coding=UTF8
import collections
from decimal import Decimal

import rapidjson as json
from django.conf import settings
from django.contrib.gis.geos import Point
from django.core.exceptions import ValidationError
from rest_framework import serializers
from rest_framework.settings import api_settings
from rest_framework.utils import humanize_datetime

from apps.core.field_serializers import JSONField
from apps.data.mixins import (
    IncrementableFieldSerializerMixin,
    OpDictFieldSerializerMixin,
    RelatedModelFieldSerializerMixin
)
from apps.data.validators import ArrayValidator, ObjectValidator, check_extension_length


class IncrementableIntegerFieldSerializer(IncrementableFieldSerializerMixin, serializers.IntegerField):
    pass


class IncrementableFloatFieldSerializer(IncrementableFieldSerializerMixin, serializers.FloatField):
    def to_internal_value(self, data):
        data = super().to_internal_value(data)
        # Don't allow NaN, Inf and -Inf
        if data != data or data in (Decimal('Inf'), Decimal('-Inf')):
            raise ValidationError(self.error_messages['invalid'])
        return data


class HStoreFileFieldSerializer(serializers.FileField):
    default_validators = [check_extension_length]
    type_name = 'FileField'

    def to_representation(self, value):
        if value:
            value = value.url
            return {'type': 'file', 'value': value}


class ReferenceFieldSerializer(RelatedModelFieldSerializerMixin, serializers.IntegerField):
    type_name = 'ReferenceField'

    def __init__(self, target, *args, **kwargs):
        self.target = target
        super().__init__(*args, **kwargs)

    def to_internal_value(self, value):
        value = super().to_internal_value(value)

        model, filter_kwargs = self.get_model_and_filter_kwargs()
        filter_kwargs['pk'] = value

        if not model.objects.filter(**filter_kwargs).exists():
            raise ValidationError('Target with specified id does not exist.')
        return value

    def to_representation(self, value):
        value = super().to_representation(value)
        if value:
            return {'type': 'reference', 'target': self.target, 'value': value}


class DateTimeFieldSerializer(serializers.DateTimeField):
    # Flag for CSerializer to know that we should serialize it as a dict structure, not like standard DateTimeField
    as_dict = 'datetime'
    type_name = 'DateTimeField'

    def to_representation(self, value):
        value = super().to_representation(value)
        if value:
            return {'type': 'datetime', 'value': value}

    def to_internal_value(self, value):
        value = super().to_internal_value(value)
        try:
            # Check if serializing works as strftime has some separate validation rules
            self.to_representation(value)
        except ValueError:
            input_formats = getattr(self, 'input_formats', api_settings.DATETIME_INPUT_FORMATS)
            humanized_format = humanize_datetime.datetime_formats(input_formats)
            self.fail('invalid', format=humanized_format)

        return value


class DataJSONFieldSerializerBase(JSONField):
    def __init__(self, *args, **kwargs):
        kwargs.pop('allow_blank', None)
        super().__init__(*args, **kwargs)

    def to_representation(self, value):
        if value and isinstance(value, str):
            return json.loads(value)
        return value


class ArrayFieldSerializer(OpDictFieldSerializerMixin, DataJSONFieldSerializerBase):
    default_error_messages = {
        'invalid': 'Not a valid array.',
    }

    ADD_OP = '_add'
    ADDUNIQUE_OP = '_addunique'
    REMOVE_OP = '_remove'

    default_validators = [ArrayValidator()]
    supported_ops = {ADD_OP, ADDUNIQUE_OP, REMOVE_OP}

    def process_value_operation(self, value, op_dict):
        value = value or []

        if self.ADD_OP in op_dict:
            value += self._to_array(op_dict[self.ADD_OP])

        if self.ADDUNIQUE_OP in op_dict:
            cur_value_set = set(value)
            for val in self._to_array(op_dict[self.ADDUNIQUE_OP]):
                try:
                    if val not in cur_value_set:
                        value.append(val)
                except TypeError:
                    raise ValidationError(self.error_messages['invalid'])

        if self.REMOVE_OP in op_dict:
            remove_value_set = set(self._to_array(op_dict[self.REMOVE_OP]))
            value = [val for val in value if val not in remove_value_set]
        return value

    def _to_array(self, value):
        if not isinstance(value, list):
            return [value]
        return value


class ObjectFieldSerializer(DataJSONFieldSerializerBase):
    default_error_messages = {
        'invalid': 'Not a valid object.',
    }
    default_validators = [ObjectValidator()]


class NullBooleanFieldSerializer(serializers.NullBooleanField):
    default_error_messages = {
        'invalid': 'Not a valid boolean.'
    }

    def to_internal_value(self, data):
        if not isinstance(data, collections.Hashable):
            self.fail('invalid')
        return super().to_internal_value(data)


class PointFieldSerializer(serializers.ModelField):
    default_error_messages = {
        'invalid': 'Not a valid geopoint.'
    }

    def to_representation(self, obj):
        value = getattr(obj, self.model_field.attname)
        if value:
            return {'type': 'geopoint', 'longitude': value.x, 'latitude': value.y}

    def _check_number(self, value, range):
        if value is not None and isinstance(value, (int, float,)) and range[0] <= value <= range[1]:
            return True
        return False

    def to_internal_value(self, value):
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except ValueError:
                pass

        if isinstance(value, dict) and 'longitude' in value and 'latitude' in value:
            longitude, latitude = value['longitude'], value['latitude']

            if not self._check_number(longitude, (-180, 180)) or not self._check_number(latitude, (-90, 90)):
                self.fail('invalid')

            value = Point(longitude, latitude)

        if not isinstance(value, Point):
            self.fail('invalid')
        return value


class RelationFieldSerializer(RelatedModelFieldSerializerMixin, ArrayFieldSerializer):
    default_validators = []
    max_length = settings.DATA_OBJECT_RELATION_LIMIT
    supported_ops = {ArrayFieldSerializer.ADD_OP, ArrayFieldSerializer.REMOVE_OP}

    def __init__(self, target, child, *args, **kwargs):
        self.target = target
        super().__init__(*args, **kwargs)

    def to_internal_value(self, value):
        value = super().to_internal_value(value)

        if not isinstance(value, list):
            raise serializers.ValidationError('Not a valid relation.')
        for element in value:
            if not isinstance(element, int):
                raise serializers.ValidationError('Relation can only contain integers (object ids).')
        if len(value) > self.max_length:
            raise serializers.ValidationError('Relation length limit exceeded (%d).' % self.max_length)

        model, filter_kwargs = self.get_model_and_filter_kwargs()
        value = list(set(value))
        filter_kwargs['pk__in'] = value
        return list(model.objects.filter(**filter_kwargs).values_list('id', flat=True))

    def to_representation(self, value):
        value = super().to_representation(value)
        if value:
            return {'type': 'relation', 'target': self.target, 'value': value}
