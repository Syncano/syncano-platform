# coding=UTF8
from abc import ABC, abstractproperty
from functools import partial

import django_filters
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db import router, transaction
from django.http import Http404
from django.views.generic import View
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import permissions, serializers, status
from rest_framework.decorators import detail_route, list_route
from rest_framework.response import Response
from rest_framework_extensions.mixins import NestedViewSetMixin as _NestedViewSetMixin
from rest_framework_extensions.settings import extensions_api_settings

from apps.admins.permissions import AdminHasPermissions
from apps.billing.permissions import OwnerInGoodStanding
from apps.core.abstract_models import CacheableAbstractModel
from apps.core.contextmanagers import revalidate_integrityerror
from apps.core.decorators import force_atomic
from apps.core.exceptions import ModelNotFound, RequestLimitExceeded
from apps.core.helpers import Cached, validate_field
from apps.core.serializers import EndpointAclSerializer, NewNameSerializer
from apps.core.signals import apiview_finalize_response, apiview_view_processed
from apps.instances.helpers import get_instance_db


class SignalSenderModelMixin:
    def perform_create(self, serializer):
        instance = serializer.save()
        apiview_view_processed.send(sender=self.model, view=self, instance=instance, action='create')

    def perform_update(self, serializer):
        instance = serializer.save()
        apiview_view_processed.send(sender=self.model, view=self, instance=instance, action='update')

    def perform_destroy(self, instance):
        instance.delete()
        apiview_view_processed.send(sender=self.model, view=self, instance=instance, action='delete')

    def finalize_response(self, request, response, *args, **kwargs):
        apiview_finalize_response.send(sender=self.model, view=self, request=request, response=response)
        return super().finalize_response(request, response, *args, **kwargs)


class AtomicMixin:
    def dispatch(self, request, *args, **kwargs):
        """
        `.dispatch()` is pretty much the same as Django's regular dispatch,
        but with extra hooks for startup, finalize, and exception handling.
        """
        self.args = args
        self.kwargs = kwargs
        request = self.initialize_request(request, *args, **kwargs)
        self.request = request
        self.headers = self.default_response_headers  # deprecate?
        self.is_atomic = False

        try:
            self.initial(request, *args, **kwargs)

            # Get the appropriate handler method
            if request.method.lower() in self.http_method_names:
                handler = getattr(self, request.method.lower(),
                                  self.http_method_not_allowed)
            else:
                handler = self.http_method_not_allowed

            force_atomic = getattr(handler, 'force_atomic', None)
            if force_atomic is None:
                force_atomic = request.method not in permissions.SAFE_METHODS

            if force_atomic:
                db = None

                # Model class router takes precedence
                model_class = getattr(self, 'model', None)
                if model_class:
                    db = router.db_for_write(model_class)
                else:
                    # Fallback to instance db
                    instance = getattr(request, 'instance', None)
                    if instance:
                        db = get_instance_db(instance)

                with transaction.atomic(db):
                    self.is_atomic = True
                    response = handler(request, *args, **kwargs)
            else:
                response = handler(request, *args, **kwargs)

        except Exception as exc:
            response = self.handle_exception(exc)

        self.response = self.finalize_response(request, response, *args, **kwargs)
        return self.response

    def get_queryset(self):
        if self.request.method not in permissions.SAFE_METHODS \
                and hasattr(self, self.request.method.lower()) \
                and self.is_atomic:
            return super().get_queryset().select_for_update(of=('self',))
        return super().get_queryset()


class NestedViewSetMixin(_NestedViewSetMixin):
    # Original one is kind of flawed as e.g. /codeboxes/qwe/traces/ generates an error as it tries to use `qwe`
    # in query as an integer. Catch ValueError and treat it as 404.

    viewset_breadcrumb = None
    parents_query_lookups = None

    def __init__(self, *args, **kwargs):
        self.viewset_breadcrumb = kwargs.pop('viewset_breadcrumb', [])
        self.parents_query_lookups = kwargs.pop('parents_query_lookups', [])
        super().__init__(*args, **kwargs)

    def get_parents_query_dict(self):
        return {lookup: self.kwargs[lookup] for lookup in self.parents_query_lookups}

    def filter_queryset_by_parents_lookups(self, queryset):
        parents_query_dict = self.get_parents_query_dict()
        if parents_query_dict and queryset is not None:
            return queryset.filter(**parents_query_dict)
        return queryset

    def initial(self, request, *args, **kwargs):
        parents_lookup_values = []

        # Get all lookup values
        for lookup in self.parents_query_lookups:
            value = kwargs.pop('%s%s' % (extensions_api_settings.DEFAULT_PARENT_LOOKUP_KWARG_NAME_PREFIX, lookup), None)
            parents_lookup_values.append(value)

        # Loop through viewset breadcrumb and get all related objects in hierarchy
        for i, parent_viewset in enumerate(self.viewset_breadcrumb):
            value = parents_lookup_values[i]
            model = getattr(parent_viewset, 'model', parent_viewset.queryset.model)

            lookup_field = parent_viewset.lookup_field
            if lookup_field == 'pk':
                field = model._meta.pk
            else:
                field = model._meta.get_field(lookup_field)

            # Validate field value first
            if not isinstance(value, model):
                try:
                    value = validate_field(field, value)
                    lookup_kwargs = {lookup_field: value}

                    if hasattr(parent_viewset, 'get_lookup'):
                        obj = parent_viewset.get_lookup(value)
                    elif issubclass(model, CacheableAbstractModel):
                        obj = Cached(model, kwargs=lookup_kwargs).get()
                    else:
                        obj = model.objects.get(**lookup_kwargs)
                except (ValidationError, ObjectDoesNotExist, ValueError):
                    # If value is not valid for a field or model not found - raise an error
                    raise ModelNotFound(model)
            else:
                obj = value

            class_name = obj.__class__.__name__.lower()
            # Optional validation of model
            validate_func = getattr(self, 'validate_{}'.format(class_name), None)
            if validate_func is not None and not validate_func(obj):
                raise ModelNotFound(model)

            # Set object as both a field and in kwargs
            setattr(self, class_name, obj)
            kwargs[self.parents_query_lookups[i]] = obj

        # Save updated kwargs
        self.kwargs = kwargs
        return super().initial(request, *args, **kwargs)


class RenameNameViewSetMixin:
    serializer_detail_class = None

    def _validate_new_name(self, field, value):
        try:
            field.run_validation(value)
        except serializers.ValidationError as exc:
            raise serializers.ValidationError({'new_name': exc.detail})

    @detail_route(methods=['post'], serializer_class=NewNameSerializer, serializer_detail_class=NewNameSerializer)
    def rename(self, request, *args, **kwargs):
        obj = self.get_object()
        serializer_class = self.__class__.serializer_class
        serializer = serializer_class(obj, context=self.get_serializer_context())

        field = serializer.fields['name']
        new_name = request.data.get('new_name')

        self._validate_new_name(field, new_name)
        obj.name = new_name

        with revalidate_integrityerror(self.model, partial(self._validate_new_name, field, new_name)):
            obj.save()

        # Set kwargs so we end up with correct new links
        self.kwargs['name'] = new_name
        return Response(serializer.data, status=status.HTTP_200_OK)


class AutocompleteMixin(View):
    autocomplete_field = 'name'
    filter_backends = (DjangoFilterBackend,)

    @classmethod
    def as_view(cls, *args, **kwargs):
        class AutocompleteFilter(django_filters.FilterSet):
            class Meta:
                model = getattr(cls, 'model', cls.queryset.model)
                fields = {cls.autocomplete_field: ['startswith']}

        cls.filter_class = AutocompleteFilter
        return super().as_view(*args, **kwargs)


class ValidateRequestSizeMixin:
    request_limit = None

    @classmethod
    def get_request_content_length(cls, request):
        meta = request.META
        try:
            return int(meta.get('HTTP_CONTENT_LENGTH', meta.get('CONTENT_LENGTH', 0)))
        except (ValueError, TypeError):
            return 0

    def initial(self, request, *args, **kwargs):
        content_length = self.get_request_content_length(request)

        if self.request_limit and content_length > self.request_limit:
            raise RequestLimitExceeded(self.request_limit)
        return super().initial(request, *args, **kwargs)


class CacheableObjectMixin:
    def get_object(self):
        lookup_url_kwarg = self.lookup_url_kwarg or self.lookup_field
        # Raise 404 also when kwargs don't match the required types
        try:
            obj = Cached(self.model, kwargs={self.lookup_field: self.kwargs[lookup_url_kwarg]}).get()
        except (self.model.DoesNotExist, TypeError, ValueError):
            raise Http404

        self.check_object_permissions(self.request, obj)
        return obj


class EndpointAclMixin(ABC):
    @abstractproperty
    def endpoint_acl_object_field(self):
        return

    def get_endpoint_acl_object(self, request):
        return request.instance

    def get_endpoint_acl(self, request):
        return getattr(self.get_endpoint_acl_object(request), self.endpoint_acl_object_field)

    def set_endpoint_acl(self, request, value):
        acl_object = self.get_endpoint_acl_object(request)
        acl_field = self.endpoint_acl_object_field
        setattr(acl_object, acl_field, value)
        acl_object.save(update_fields=(acl_field,))

    @list_route(serializer_class=EndpointAclSerializer,
                methods=['get', 'put', 'patch'],
                permission_classes=(OwnerInGoodStanding, AdminHasPermissions))
    def acl(self, request, **kwargs):
        obj = {'acl': self.get_endpoint_acl(request)}

        if request.method == 'GET':
            serializer = self.get_serializer(obj)
            return Response(serializer.data)

        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            self.set_endpoint_acl(request, serializer.data['acl'])
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class GenericEndpointViewSetMixin:
    as_endpoint = True

    def process_endpoint(self):
        raise NotImplementedError  # pragma: no cover


class EndpointViewSetMixin(GenericEndpointViewSetMixin):
    def endpoint_get(self, request, *args, **kwargs):
        return self.process_endpoint()

    @force_atomic(False)
    def endpoint_post(self, request, *args, **kwargs):
        return self.process_endpoint()

    @force_atomic(False)
    def endpoint_patch(self, request, *args, **kwargs):
        return self.process_endpoint()

    @force_atomic(False)
    def endpoint_put(self, request, *args, **kwargs):
        return self.process_endpoint()

    @force_atomic(False)
    def endpoint_delete(self, request, *args, **kwargs):
        return self.process_endpoint()
