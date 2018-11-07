# coding=UTF8
from apps.core.exceptions import MalformedPageParameter
from apps.core.pagination import StandardPagination


class RedisStandardPagination(StandardPagination):
    validate_fields = False

    def paginate_queryset(self, queryset, request, view=None):
        """
        Paginate a queryset if required, either returning a page object,
        or `None` if pagination is not configured for this view.
        """

        self.max_page_size = getattr(view, 'max_page_size', self.max_page_size)
        self.page_size = self.get_page_size(request)
        self.request = request
        self.paginate_query_params = self.default_paginate_query_params + getattr(view, 'paginate_query_params', ())
        self.order_asc = self.get_ordering(queryset, request) == 'asc'

        return self.get_page(queryset, request, view)

    def get_page(self, queryset, request, view=None):
        cursor = self.cursor = self.get_cursor(queryset, request)
        page_size = self.page_size

        self.has_next = None
        self.has_prev = None
        min_pk = None
        max_pk = None
        forward = cursor.direction != 0

        # Setup filtering
        if cursor.last_pk is not None:
            if self.order_asc is forward:
                min_pk = cursor.last_pk
            else:
                max_pk = cursor.last_pk

            # Offset 1 so that we make a non-inclusive filter
            if min_pk is not None:
                min_pk += 1
            elif max_pk is not None:
                max_pk -= 1

        if not forward:
            self.order_asc = not self.order_asc

        # Process min/max pk from view.kwargs
        min_pk_list = (view.kwargs.pop('min_pk', None), min_pk)
        min_pk = max(v for v in min_pk_list if v is not None) if any(min_pk_list) else None
        max_pk_list = (view.kwargs.pop('max_pk', None), max_pk)
        max_pk = min(v for v in max_pk_list if v is not None) if any(max_pk_list) else None

        # List objects
        object_list = queryset.list(min_pk=min_pk,
                                    max_pk=max_pk,
                                    ordering='asc' if self.order_asc else 'desc',
                                    limit=self.page_size,
                                    **view.kwargs)

        has_more = len(object_list) >= page_size

        if forward:
            self.has_next = has_more
            self.object_list = object_list
        else:
            self.has_prev = has_more
            self.object_list = object_list[page_size::-1]

        if self.has_next is True or self.has_prev is True or self.cursor.last_pk is not None:
            self.display_page_controls = True

        return self.object_list

    def get_cursor_params(self, queryset, request):
        direction, last_pk = super().get_cursor_params(queryset, request)

        if last_pk is not None:
            try:
                last_pk = int(last_pk)
            except ValueError:
                raise MalformedPageParameter
        return direction, last_pk

    def get_queryset_order_by(self, queryset):
        return queryset.default_ordering
