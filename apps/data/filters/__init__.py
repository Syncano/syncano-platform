# coding=UTF8
import rapidjson as json
from django.core.exceptions import ValidationError
from django.db.models import FieldDoesNotExist, Q
from django.db.models.sql import EmptyResultSet
from rest_framework import filters

from apps.core.helpers import get_from_request_query_params
from apps.data.exceptions import InvalidQuery
from apps.data.filters.lookups import lookup_registry
from apps.data.validators import validate_query


class QueryFilterBackend(filters.BaseFilterBackend):
    """
    Query filter based on GET query param.
    Currently supports only AND logic in form of:
    ```{"field_name": {"_lookup": "value", "_lookup2": "value2"}}```

    For example:
    ```{"field_name": {"_gt": 1, "_lte": 5}}```

    Possible lookups: _gt, _gte, _lt, _lte, _eq, _neq, _exists, _in.
    """

    def process_query(self, view, queryset, query, query_fields=None, query_fields_extra=None):
        query_fields = query_fields or getattr(view, 'query_fields', {})
        query_fields_extra = query_fields_extra or getattr(view, 'query_fields_extra', {})
        current_q = Q()

        for field_name, lookups in query.items():
            field, field_desc = self.get_field_info(field_name, query_fields_extra, queryset.model)

            # Respect virtual field settings
            if field.column is None:
                can_filter = field.filter_index
            else:
                can_filter = field_name in query_fields

            if not can_filter:
                raise InvalidQuery('Field "{field_name}" cannot be used in a query as it is not indexed.'.format(
                    field_name=field_name
                ))

            if not isinstance(lookups, dict):
                raise InvalidQuery('Invalid field "{field_name}" lookup type. Expected JSON object.'.format(
                    field_name=field_name))

            for lookup, value in lookups.items():
                lookup_obj = lookup_registry.match(lookup, field)

                if lookup_obj is None:
                    raise InvalidQuery('Invalid lookup "{lookup}" defined for field "{field_name}".'.format(
                        field_name=field_name, lookup=lookup))

                value = lookup_obj.validate_value(view, field, value)
                current_q &= lookup_obj.get_q(field_desc['lookup'], value)

        return queryset.filter(current_q)

    def filter_queryset(self, request, queryset, view):
        queries = get_from_request_query_params(request, 'query', getlist=True)

        for query in queries:
            if query:
                if isinstance(query, str):
                    try:
                        query = json.loads(query)
                    except ValueError:
                        raise InvalidQuery('Not a valid JSON string.')

                try:
                    validate_query(query)
                except ValidationError as ex:
                    raise InvalidQuery(ex.messages)

                try:
                    queryset = self.process_query(view, queryset, query)
                except EmptyResultSet:
                    return queryset.model.objects.none()

        return queryset

    def get_field_info(self, field_name, fields_extra, model):
        if field_name in fields_extra:
            field_desc = fields_extra[field_name]

            for path in field_desc['lookup'].split('__'):
                field = model._meta.get_field(path)
                if field.related_model:
                    model = field.related_model
            field.alias = field_name

        else:
            try:
                field = model._meta.get_field(field_name)
            except FieldDoesNotExist:
                raise InvalidQuery('Invalid field name defined: "{field_name}".'.format(
                    field_name=field_name))

            field_desc = {
                'lookup': field.name,
                'type': None
            }
        return field, field_desc
