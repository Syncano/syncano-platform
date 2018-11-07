# coding=UTF8
from collections import namedtuple
from datetime import datetime

import rapidjson as json
from django.conf import settings
from django.db import connection
from django.db.models import FieldDoesNotExist, Q
from django.template import loader
from rest_framework.pagination import BasePagination, _positive_int
from rest_framework.response import Response
from rest_framework.settings import api_settings
from urlobject import URLObject

from apps.core.exceptions import MalformedPageParameter, OrderByIncorrect
from apps.core.helpers import get_from_request_query_params, validate_field

Cursor = namedtuple('Cursor', ['direction', 'last_pk'])


class StandardPagination(BasePagination):
    """
    If you need to support ordering as well, use OrderedPaginationMixin.
    """

    page_size = api_settings.PAGE_SIZE
    max_page_size = settings.MAX_PAGE_SIZE
    paginate_by_param = 'page_size'
    page_direction_param = 'direction'
    page_last_pk_param = 'last_pk'
    template = 'rest_framework/pagination/previous_and_next.html'
    pagination_enabled = True
    validate_fields = True

    default_paginate_query_params = ('page_size', 'ordering',)

    def paginate_queryset(self, queryset, request, view=None):
        """
        Paginate a queryset if required, either returning a page object,
        or `None` if pagination is not configured for this view.
        """

        if not getattr(view, 'pagination_enabled', True):
            self.pagination_enabled = False
            return queryset

        self.max_page_size = getattr(view, 'max_page_size', self.max_page_size)
        if request.version in ('v1', 'v1.1'):
            self.max_page_size = self.page_size

        self.page_size = self.get_page_size(request)
        self.order_by = None
        self.order_asc = self.get_ordering(queryset, request) == 'asc'
        self.request = request
        self.paginate_query_params = self.default_paginate_query_params + getattr(view, 'paginate_query_params', ())

        return self.get_page(queryset, request, view)

    def get_page(self, queryset, request, view=None):
        page_size = self.page_size
        self.cursor = self.get_cursor(queryset, request)

        # Run actual pagination process
        queryset, reverse = self._process_object_pagination(queryset, self.cursor)

        # Standard filtering and reverse if needed
        self.has_next = None
        self.has_prev = None

        if page_size == 0:
            self.object_list = []
            return self.object_list

        object_list = list(queryset[:page_size])
        has_more = len(object_list) >= page_size

        if reverse:
            self.has_prev = has_more
            self.object_list = object_list[page_size::-1]
        else:
            self.has_next = has_more
            self.object_list = object_list

        if self.has_next is True or self.has_prev is True or self.cursor.last_pk is not None:
            self.display_page_controls = True

        return self.object_list

    def _process_object_pagination(self, queryset, cursor):
        # Ordering
        ordering = 'pk' if self.order_asc else '-pk'
        queryset = queryset.order_by(ordering)

        if cursor.direction is not None:
            return self._process_paginated_queryset(queryset, cursor)
        return queryset, False

    def _process_paginated_queryset(self, queryset, cursor):
        reverse = False
        forward = bool(cursor.direction)
        last_pk = cursor.last_pk

        # Based on ordering, reverse and conditions should be swap places
        if not self.order_asc:
            forward = not forward

        if last_pk is not None:
            if forward:
                queryset = queryset.filter(pk__gt=last_pk)
            else:
                queryset = queryset.filter(pk__lt=last_pk)

        # To maintain proper order and expected results, double reverse if needed
        if self.order_asc is not forward:
            reverse = True
            queryset = queryset.reverse()
        return queryset, reverse

    def get_page_size(self, request):
        page_size = request.query_params.get(self.paginate_by_param, self.page_size)
        try:
            return _positive_int(page_size, cutoff=self.max_page_size)
        except ValueError:
            raise MalformedPageParameter()

    def get_ordering(self, queryset, request):
        ordering = request.query_params.get('ordering')
        if ordering:
            ordering = ordering.lower()
            if ordering in ('asc', 'desc'):
                return ordering
        return self.get_queryset_order_by(queryset)

    def get_queryset_order_by(self, queryset):
        if queryset.query.order_by:
            order_by = queryset.query.order_by[0]
        else:
            order_by = queryset.model._meta.ordering[0]
        return 'desc' if order_by[0] == '-' else 'asc'

    def get_cursor_params(self, queryset, request):
        direction = get_from_request_query_params(request, self.page_direction_param)
        last_pk = get_from_request_query_params(request, self.page_last_pk_param)

        if direction is not None:
            try:
                direction = int(direction)
            except ValueError:
                raise MalformedPageParameter()

            if direction not in (0, 1):
                raise MalformedPageParameter()

        if self.validate_fields and last_pk is not None:
            pk_field = queryset.model._meta.pk
            last_pk = self.validate_field_value(pk_field, last_pk)
        return direction, last_pk

    def get_cursor(self, queryset, request):
        return Cursor(*self.get_cursor_params(queryset, request))

    def validate_field_value(self, field, value):
        try:
            return validate_field(field, value, validate_none=False)
        except Exception:
            # Every error is a user error! Bad user!
            raise MalformedPageParameter()

    def get_next_cursor(self):
        object_list = self.object_list
        if self.has_next is False:
            return
        if object_list and len(object_list) == self.page_size:
            return Cursor(direction=1, last_pk=object_list[-1].pk)
        elif self.cursor.direction == 0:
            return Cursor(direction=None, last_pk=None)

    def get_previous_cursor(self):
        object_list = self.object_list
        if self.cursor.direction is None or self.has_prev is False:
            return
        if not object_list:
            if self.cursor.direction == 1:
                return Cursor(direction=0, last_pk=None)
        elif len(object_list) == self.page_size or self.cursor.direction == 1:
            return Cursor(direction=0, last_pk=object_list[0].pk)

    def encode_cursor(self, cursor):
        return {k: str(v) for k, v in cursor._asdict().items() if v is not None}

    def get_next_link(self):
        cursor = self.get_next_cursor()
        return self.get_cursor_link(cursor)

    def get_previous_link(self):
        cursor = self.get_previous_cursor()
        return self.get_cursor_link(cursor)

    def get_cursor_link(self, cursor):
        if not cursor:
            return

        request = self.request
        url = request and request.path or ''
        url_object = URLObject(url)
        get_params = self.default_paginate_query_params

        for param in get_params:
            value = request.query_params.get(param)

            if value is not None:
                if not isinstance(value, str):
                    value = json.dumps(value)
                url_object = url_object.set_query_param(param, value)

        encoded_cursor = self.encode_cursor(cursor)
        for param, value in encoded_cursor.items():
            url_object = url_object.set_query_param(param, value)

        return str(url_object)

    def get_paginated_response(self, data):
        if self.pagination_enabled:
            return Response({
                'next': self.get_next_link(),
                'prev': self.get_previous_link(),
                'objects': data
            })
        return Response({'objects': data})

    def get_html_context(self):
        return {
            'previous_url': self.get_previous_link(),
            'next_url': self.get_next_link()
        }

    def to_html(self):
        template = loader.get_template(self.template)
        context = self.get_html_context()
        return template.render(context)


OrderedCursor = namedtuple('Cursor', ['direction', 'last_pk', 'last_value'])


class OrderedPagination(StandardPagination):
    """
    You can define additional orderable_fields that should be supported on a view.
    """

    ordering_param = 'order_by'
    page_last_value_param = 'last_value'
    default_paginate_query_params = ('page_size', 'order_by',)

    def paginate_queryset(self, queryset, request, view=None):
        if view:
            self.order_fields = getattr(view, 'order_fields', set())
        else:
            self.order_fields = set()

        return super().paginate_queryset(queryset, request, view)

    def get_cursor_params(self, queryset, request):
        page_last_value = get_from_request_query_params(self.request, self.page_last_value_param)
        return super().get_cursor_params(queryset, request) + (page_last_value,)

    def get_cursor(self, queryset, request):
        return OrderedCursor(*self.get_cursor_params(queryset, request))

    def _process_object_pagination(self, queryset, cursor):
        self.order_by = get_from_request_query_params(self.request, self.ordering_param)
        self.order_by_field = None

        if self.order_by is not None:
            return self._process_ordered_pagination(queryset, cursor)

        if cursor.direction is not None:
            # Standard pagination as order by is not defined
            return self._process_paginated_queryset(queryset, cursor)
        return queryset, False

    def _process_ordered_pagination(self, queryset, cursor):
        # For order_by use keyset (seek method) pagination
        order_asc = self.order_asc = True
        order_by = order_by_field = self.order_by
        pk_order = 'pk'

        if order_by.startswith('-'):
            pk_order = '-pk'
            order_by_field = order_by[1:]
            order_asc = self.order_asc = False

        self.order_by_field = order_by_field

        # Check if field actually exists
        try:
            order_field = queryset.model._meta.get_field(order_by_field)
        except FieldDoesNotExist:
            raise OrderByIncorrect()

        if order_field.column is None:
            # We're dealing with a virtual field (hstore based) so we need to check if it is indexed
            order_field_column = self._get_virtual_field_column(order_field)
            field_order = 'order_field'
            if not order_asc:
                field_order = '-order_field'

            queryset = queryset.extra(
                select={'order_field': order_field_column},
                order_by=[field_order, pk_order])
        else:
            # If we're not dealing with a virtual field, we can do it in a more sane way
            if order_by_field not in self.order_fields:
                raise OrderByIncorrect('Cannot use specified order_by field.')

            if order_by_field == queryset.model._meta.pk.name:
                # This is not keyset pagination, we can wrap this up in standard pagination
                return super()._process_object_pagination(queryset, cursor)

            qn = connection.ops.quote_name
            queryset = queryset.order_by(order_by, pk_order)
            order_field_column = '{table}.{column}'.format(table=qn(queryset.model._meta.db_table),
                                                           column=qn(order_field.column))

        if cursor.direction is not None:
            return self._process_ordered_paginated_queryset(queryset,
                                                            cursor,
                                                            order_field=order_field,
                                                            column=order_field_column,
                                                            is_ascending=order_asc)

        return queryset, False

    def _process_ordered_paginated_queryset(self, queryset, cursor, order_field, column,
                                            is_ascending):
        reverse = False
        forward = bool(cursor.direction)
        last_pk = cursor.last_pk
        qn = connection.ops.quote_name

        # Validate field value
        last_value = self.validate_field_value(order_field, cursor.last_value)

        # Based on ordering and direction, query may need to be reversed
        if not is_ascending:
            forward = not forward

        if last_pk:
            pk_field = queryset.model._meta.pk.name

            # To support nullable values, we need to change the query based on last_value being null or not
            if forward:
                # Ascending
                if last_value is None:
                    # Nulls Last, so if we got null value, find more nulls that have higher pk
                    queryset = queryset.filter(
                        Q(**{'{field}__isnull'.format(field=order_field.name): True}) & Q(pk__gt=last_pk))
                else:
                    # Null value not yet reached, look for null values or with higher pair
                    where_sql = '{order_field} IS NULL ' \
                                'OR ({order_field}, {table}.{pk_field}) > (%s, %s)'
                    where_sql = where_sql.format(table=qn(queryset.model._meta.db_table), order_field=column,
                                                 pk_field=qn(pk_field))
                    queryset = queryset.extra(where=[where_sql], params=[last_value, last_pk])
            else:
                # Descending
                if last_value is None:
                    # Null value reached, look for values that are not null or other nulls with lower pk
                    queryset = queryset.filter(
                        Q(**{'{field}__isnull'.format(field=order_field.name): False}) |
                        (Q(pk__lt=last_pk) & Q(**{'{field}__isnull'.format(field=order_field.name): True})))
                else:
                    # Last value was not null, so proceed normally
                    where_sql = '({order_field}, {table}.{pk_field}) < (%s, %s)'.format(
                        table=qn(queryset.model._meta.db_table), order_field=column, pk_field=qn(pk_field))
                    queryset = queryset.extra(where=[where_sql], params=[last_value, last_pk])

        # To maintain proper order and expected results, double reverse if needed
        if is_ascending != forward:
            reverse = True
            queryset = queryset.reverse()
        return queryset, reverse

    def _get_virtual_field_column(self, order_field):
        if not order_field.order_index:
            raise OrderByIncorrect('Cannot use specified order_by field. Set required index on schema first.')

        # Sadly virtual field needs to have .column set to None to prevent Django from going crazy
        # we need to get the column on our own and order by .extra
        column = order_field.db_field(connection.ops.quote_name, connection)
        return column

    def get_next_cursor(self):
        if self.has_next is False:
            return
        order_by_field = getattr(self, 'order_by_field', None)

        if order_by_field is not None:
            object_list = self.object_list
            if object_list and len(object_list) == self.page_size:
                last_object = object_list[-1]

                order_field_value = getattr(last_object, order_by_field)
                order_field_value = self._prepare_order_field(order_field_value)

                return OrderedCursor(1, last_object.pk, order_field_value)
            elif self.cursor.direction == 0:
                return OrderedCursor(None, None, None)
            return
        return super().get_next_cursor()

    def get_previous_cursor(self):
        if self.has_prev is False:
            return
        order_by_field = getattr(self, 'order_by_field', None)

        if order_by_field is not None:
            object_list = self.object_list
            if self.cursor.direction is None:
                return

            if not object_list:
                if self.cursor.direction == 1:
                    return OrderedCursor(0, None, None)
            elif len(object_list) == self.page_size or self.cursor.direction == 1:
                first_object = object_list[0]

                order_field_value = getattr(first_object, order_by_field)
                order_field_value = self._prepare_order_field(order_field_value)

                return OrderedCursor(0, first_object.pk, order_field_value)
            return
        return super().get_previous_cursor()

    def _prepare_order_field(self, order_field):
        # Process datetime if needed as it does not serialize properly with json
        if isinstance(order_field, datetime):
            order_field = order_field.strftime(settings.DATETIME_FORMAT)

        return order_field
