# coding=UTF8
from collections import defaultdict

from django.conf import settings
from django.contrib.gis.geos import Point
from django.contrib.gis.measure import Distance
from django.core.exceptions import ValidationError
from django.db.models import AutoField, CharField, ForeignKey, Q
from django.db.models.expressions import RawSQL
from rest_framework.validators import UniqueValidator

from apps.core.helpers import Cached
from apps.core.validators import validate_id
from apps.data.contextmanagers import loaded_klass
from apps.data.exceptions import InvalidQuery
from apps.data.fields import ArrayField, PointField, ReferenceField, RelationField
from apps.data.filters.mixins import ListValidationMixin
from apps.data.models import DataObject, Klass

LOOKUP_PREFIX = '_'


class LookupRegistry(defaultdict):
    def register(self, lookup):
        self['{lookup_prefix}{lookup}'.format(lookup_prefix=LOOKUP_PREFIX, lookup=lookup.lookup)].append(lookup)

    def match(self, lookup, field):
        for lookup_obj in self[lookup]:
            if lookup_obj.is_field_supported(field):
                return lookup_obj


lookup_registry = LookupRegistry(list)


class Lookup:
    supported_types = ()
    unsupported_types = (ArrayField, PointField, RelationField)

    expected_value_type = None
    allow_none_value = False
    default_error = 'Invalid value type provided for "{lookup}" lookup of field "{field_name}".'
    validation_error = 'Validation of value provided for "{lookup}" lookup of field "{field_name}" failed: ' \
                       '{validation_error}'
    max_value_length = 128

    def __init__(self, lookup):
        self.lookup = lookup

    def is_field_supported(self, field):
        if self.supported_types:
            return isinstance(field, self.supported_types)
        return not isinstance(field, self.unsupported_types)

    def validate_value(self, view, field, value, expected_value_type=None):
        expected_value_type = expected_value_type or self.expected_value_type
        field_name = getattr(field, 'alias', field.name)

        if not self.allow_none_value and value is None:
            raise InvalidQuery(self.default_error.format(lookup=self.lookup, field_name=field_name))

        if expected_value_type is None:
            try:
                value = field.to_python(value)
                if isinstance(field, (AutoField, ForeignKey)):
                    validate_id(value)

                # run validators on value (skip unique validators)
                for v in [v for v in field.validators if not isinstance(v, UniqueValidator)]:
                    v(value)
            except ValidationError as ex:
                message = ex.message
                if ex.params:
                    message %= ex.params

                raise InvalidQuery(self.validation_error.format(
                    lookup=self.lookup, field_name=field_name, validation_error=message))
            except Exception:
                raise InvalidQuery(self.default_error.format(lookup=self.lookup, field_name=field_name))

        else:
            if not isinstance(value, expected_value_type) or \
                    (isinstance(value, str) and len(value) > self.max_value_length):
                raise InvalidQuery(self.default_error.format(lookup=self.lookup, field_name=field_name))

        return value

    def get_q(self, field_name, value):
        raise NotImplementedError  # pragma: no cover


class SimpleLookup(Lookup):
    def __init__(self, lookup, orm_lookup=None):
        if orm_lookup is None:
            orm_lookup = lookup
        self.orm_lookup = orm_lookup
        super().__init__(lookup)

    def get_q(self, field_name, value):
        return Q(**{'{field_name}__{orm_lookup}'.format(field_name=field_name, orm_lookup=self.orm_lookup): value})


lookup_registry.register(SimpleLookup('gt'))
lookup_registry.register(SimpleLookup('gte'))
lookup_registry.register(SimpleLookup('lt'))
lookup_registry.register(SimpleLookup('lte'))
lookup_registry.register(SimpleLookup('eq', 'exact'))


class ExistsLookup(Lookup):
    expected_value_type = bool
    unsupported_types = (ArrayField,)

    def __init__(self):
        super().__init__('exists')

    def get_q(self, field_name, value):
        # Exists and isnull have opposite logic value
        value = not value
        return Q(**{'{field_name}__isnull'.format(field_name=field_name): value})


lookup_registry.register(ExistsLookup())


class NotEqualLookup(Lookup):
    def __init__(self):
        super().__init__('neq')

    def get_q(self, field_name, value):
        return ~Q(**{'{field_name}__exact'.format(field_name=field_name): value})


lookup_registry.register(NotEqualLookup())


class InLookup(ListValidationMixin, SimpleLookup):
    def __init__(self):
        super().__init__('in')


lookup_registry.register(InLookup())


class NotInLookup(InLookup):
    def __init__(self):
        super(InLookup, self).__init__('nin', 'in')

    def get_q(self, field_name, value):
        q = super().get_q(field_name, value)
        return ~q


lookup_registry.register(NotInLookup())


class StringLookup(SimpleLookup):
    supported_types = (CharField,)
    allowed_columns = ('username',)

    def validate_value(self, view, field, value, expected_value_type=None):
        # Do not allow filtering on built-in string fields, only user fields
        if field.column is not None and field.column not in self.allowed_columns:
            raise InvalidQuery('{lookup} is not supported on this field type.'.format(
                lookup=self.lookup,
            ))
        return super().validate_value(view, field, value, expected_value_type)


for string_lookup in ('contains', 'icontains', 'startswith', 'istartswith', 'endswith', 'iendswith', 'like', 'ilike'):
    lookup_registry.register(StringLookup(string_lookup))
lookup_registry.register(StringLookup('ieq', 'iexact'))


class ReferenceIsLookup(SimpleLookup):
    supported_types = (ReferenceField,)

    def __init__(self):
        super().__init__('is', 'in')

    def validate_value(self, view, field, value, expected_value_type=None):
        target = field.target
        query_fields = None
        query_fields_extra = None
        id_field = 'id'

        if target == 'user':
            # For target=user, use query_fields from v2 UserViewSet
            from apps.users.v2.views import UserViewSet

            target = 'user_profile'
            query_fields = UserViewSet.query_fields
            query_fields_extra = UserViewSet.query_fields_extra
            id_field = 'owner_id'

        if target == 'self':
            klass = view.klass
        else:
            try:
                klass = Cached(Klass, kwargs=dict(name=target)).get()
            except Klass.DoesNotExist:
                raise InvalidQuery('Referenced class "{klass}" does not exist.'.format(klass=target))

        with loaded_klass(klass):
            queryset = DataObject.objects.values(id_field).filter(_klass=klass)

            for filter_backend in view.filter_backends:
                queryset = filter_backend().process_query(view, queryset, value,
                                                          query_fields=query_fields,
                                                          query_fields_extra=query_fields_extra)
            queryset = queryset[:settings.DATA_OBJECT_NESTED_QUERY_LIMIT]
            return RawSQL(*queryset.query.get_compiler(using=queryset.db).as_sql())


lookup_registry.register(ReferenceIsLookup())


class ArrayLookup(ListValidationMixin, SimpleLookup):
    supported_types = (ArrayField,)
    expected_value_type = (str, bool, int, float)

    def __init__(self):
        super().__init__('contains', 'data_contains')


lookup_registry.register(ArrayLookup())


class GeoNearLookup(SimpleLookup):
    supported_types = (PointField,)
    expected_value_type = dict

    def __init__(self):
        super().__init__('near', 'geo_dwithin')

    def _check_number(self, value, range, inclusive=False):
        if value is not None and isinstance(value, (int, float,)):
            if (not inclusive and range[0] < value < range[1]) or (inclusive and range[0] <= value <= range[1]):
                return True
        return False

    def validate_value(self, view, field, value, expected_value_type=None):
        value = super().validate_value(view, field, value, expected_value_type)

        if 'longitude' not in value or 'latitude' not in value:
            raise InvalidQuery(self.default_error.format(lookup=self.lookup, field_name=field.name))

        longitude, latitude = value['longitude'], value['latitude']

        if not self._check_number(longitude, (-180, 180)) or not self._check_number(latitude, (-90, 90)):
            raise InvalidQuery('Invalid longitude/latitude values.')

        # Default distance is 100 miles
        distance_unit = 'mi'
        distance = 100
        max_distance = None

        if 'distance_in_miles' in value:
            distance = value['distance_in_miles']
            # Equator length is 24901 miles
            max_distance = 24901
        elif 'distance_in_kilometers' in value:
            distance = value['distance_in_kilometers']
            distance_unit = 'km'
            # Equator length is 40075 km
            max_distance = 40075

        if max_distance is not None and not self._check_number(distance, (0, max_distance), inclusive=True):
            raise InvalidQuery('Invalid distance value.')

        return Point(longitude, latitude), Distance(**{distance_unit: distance})


lookup_registry.register(GeoNearLookup())


class RelationContainsLookup(ArrayLookup):
    supported_types = (RelationField,)
    expected_value_type = int


lookup_registry.register(RelationContainsLookup())


class RelationIsLookup(ReferenceIsLookup):
    supported_types = (RelationField,)

    def __init__(self):
        super(ReferenceIsLookup, self).__init__('is', 'data_overlap')

    def validate_value(self, view, field, value, expected_value_type=None):
        rawsql = super().validate_value(view, field, value, expected_value_type)
        rawsql.sql = 'ARRAY({})'.format(rawsql.sql)
        # needed conversion for data_overlap to join parameters properly
        rawsql.params = list(rawsql.params)
        return rawsql


lookup_registry.register(RelationIsLookup())
