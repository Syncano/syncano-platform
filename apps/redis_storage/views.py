# coding=UTF8
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.http import Http404
from rest_framework.pagination import _positive_int
from rest_framework.response import Response
from rest_framework.settings import api_settings
from rest_framework.viewsets import GenericViewSet

from apps.core.exceptions import MalformedPageParameter
from apps.redis_storage.pagination import RedisStandardPagination


class ReadOnlyModelViewSet(GenericViewSet):
    page_size = api_settings.PAGE_SIZE
    max_page_size = settings.MAX_PAGE_SIZE
    paginate_by_param = 'page_size'
    ordering = 'desc'
    pagination_class = RedisStandardPagination

    def get_page_size(self, request):
        page_size = request.query_params.get(self.paginate_by_param, self.page_size)
        try:
            return _positive_int(page_size, cutoff=self.max_page_size)
        except ValueError:
            raise MalformedPageParameter()

    def get_ordering(self, request):
        ordering = request.query_params.get('ordering')
        if ordering:
            ordering = ordering.lower()
            if ordering in ('asc', 'desc'):
                return ordering
        return self.ordering

    def retrieve(self, request, pk, *args, **kwargs):
        try:
            object = self.model.get(pk=pk)
        except ObjectDoesNotExist:
            raise Http404

        serializer = self.get_serializer(object)
        return Response(serializer.data)

    def get_queryset(self):
        # Workaround so that browsable API does not complain.
        return

    def list(self, request, *args, **kwargs):
        page = self.paginate_queryset(self.model)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(self.model.list(limit=self.get_page_size(request),
                                                         ordering=self.get_ordering(request),
                                                         **self.kwargs),
                                         many=True)
        return Response(serializer.data)
