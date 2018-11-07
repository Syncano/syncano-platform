# coding=UTF8
from collections import defaultdict

from rest_condition import Or
from rest_framework import status, viewsets
from rest_framework.decorators import detail_route
from rest_framework_extensions.mixins import DetailSerializerMixin
from rest_framework_extensions.settings import extensions_api_settings

from apps.admins.permissions import AdminHasPermissions
from apps.apikeys.permissions import ApiKeyHasPermissions
from apps.billing.permissions import OwnerInGoodStanding
from apps.core.helpers import run_api_view
from apps.core.mixins.views import AtomicMixin, RenameNameViewSetMixin
from apps.high_level.models import DataObjectHighLevelApi
from apps.high_level.permissions import AllowedToClearCache
from apps.high_level.v1.serializers import DataObjectHighLevelApiDetailSerializer, DataObjectHighLevelApiSerializer
from apps.instances.mixins import InstanceBasedMixin
from apps.response_templates.models import (
    RESPONSE_TEMPLATE_GET_ARG_NAMES,
    RESPONSE_TEMPLATE_HEADER_NAMES,
    ResponseTemplate
)

LOOKUP_PREFIX = extensions_api_settings.DEFAULT_PARENT_LOOKUP_KWARG_NAME_PREFIX


class DataObjectHighLevelApiViewSetBase(AtomicMixin,
                                        InstanceBasedMixin,
                                        DetailSerializerMixin,
                                        RenameNameViewSetMixin,
                                        viewsets.ModelViewSet):
    lookup_field = 'name'
    model = DataObjectHighLevelApi
    queryset = DataObjectHighLevelApi.objects.all()
    serializer_class = DataObjectHighLevelApiSerializer
    serializer_detail_class = DataObjectHighLevelApiDetailSerializer
    permission_classes = (
        Or(AdminHasPermissions, ApiKeyHasPermissions),
        OwnerInGoodStanding,
    )

    def get_queryset(self):
        queryset = super().get_queryset()
        return queryset.select_related('klass')

    def get_permissions(self):
        if self.action in ('clear_cache', ):
            self.permission_classes = (AllowedToClearCache, )
        return super().get_permissions()

    def run_view(self, request, *args, **kwargs):
        self.object = self.get_object()
        # store the template_response name, before pop;
        template_response = ResponseTemplate.get_name_from_request(request)
        self.copy_request(request)
        self.populate_request(request, self.object)

        response = self.run_data_api_view(request)
        response = self.expand(request, response)
        if template_response:
            # assign again template_response for proper rendering;
            request._request.GET[RESPONSE_TEMPLATE_GET_ARG_NAMES[0]] = template_response
        return response

    def expand(self, request, response):
        reference_fields = self.get_reference_fields()
        fields = self.get_expand_fields(request)

        if not fields or response.status_code != status.HTTP_200_OK:
            return response

        objects = response.data['objects']
        get_params = request._request.GET.copy()

        for field in fields:
            target = reference_fields[field]
            kwargs = {}

            if target != 'user':
                kwargs['%s_klass' % LOOKUP_PREFIX] = target

            objects_map = defaultdict(list)
            for obj in objects:
                if field in obj and obj[field]:  # we cannot expand something that user not requested;
                    objects_map[obj[field]['value']].append(obj)

            self.copy_request(self.request)
            request._request.GET = {'query': {'id': {'_in': list(objects_map.keys())}}}

            if target == 'user':
                subresponse = self.run_user_api_view(request, **kwargs)
            else:
                subresponse = self.run_data_api_view(request, **kwargs)

            if subresponse.status_code != status.HTTP_200_OK:
                return subresponse

            # Set objects
            for sub_obj in subresponse.data['objects']:
                for obj in objects_map[sub_obj['id']]:
                    obj[field] = sub_obj

        request._request.GET = get_params
        return response

    def copy_request(self, request):
        get_params = request._request.GET.copy()

        for param_name in RESPONSE_TEMPLATE_GET_ARG_NAMES:
            get_params.pop(param_name, None)  # pop the template to allow to render child view normally;
        for header_name in RESPONSE_TEMPLATE_HEADER_NAMES:
            request._request.META.pop(header_name, None)

        request._request.GET = get_params

    def populate_request(self, request, obj):
        possible_fields = DataObjectHighLevelApi.get_possible_fields()

        for field in possible_fields:
            value = getattr(obj, field, None)
            get_value = request.GET.get(field)

            if value and get_value and field == 'query':
                # this will add another query object eg: ?query=xx&query=yy
                request.GET.update({'query': value})
            elif value and not get_value:
                request.GET[field] = value

    def run_data_api_view(self, request, **kwargs):
        return run_api_view('dataobject-list', (request.instance.name, self.object.klass.name),
                            request, **kwargs)

    def run_user_api_view(self, request, **kwargs):
        return run_api_view('user-list', (request.instance.name,),
                            request, **kwargs)

    def get_reference_fields(self):
        if not hasattr(self, '_reference_fields'):
            self._reference_fields = {}
            klass = self.object.klass

            for field in klass.schema:
                if field['type'] != 'reference':
                    continue

                target = klass.name if field['target'] == 'self' else field['target']
                self._reference_fields[field['name']] = target

        return self._reference_fields

    def get_expand_fields(self, request):
        allowed = self.get_reference_fields()
        fields = request.GET.get('expand') or ''
        fields = [field for field in set(fields.split(',', 64)) if field in allowed]
        return fields


class DataObjectHighLevelApiViewSet(DataObjectHighLevelApiViewSetBase):
    @detail_route(methods=['get'], url_path='get')
    def get_api(self, request, *args, **kwargs):
        return self.run_view(request, *args, **kwargs)

    @detail_route(methods=['post'], url_path='post', permission_classes=(OwnerInGoodStanding,))
    def post_api(self, request, *args, **kwargs):
        self.object = self.get_object()
        return self.run_data_api_view(request)
