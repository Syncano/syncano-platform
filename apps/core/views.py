# coding=UTF8
from django.conf import settings
from django.core.exceptions import ValidationError
from django.http import HttpResponse
from rest_framework import exceptions, permissions, serializers, status, views
from rest_framework.response import Response
from rest_framework.reverse import reverse
from rest_framework.settings import api_settings
from rest_framework.views import APIView

from apps.core.renderers import JSONRenderer


def health_check(request):
    return HttpResponse(status=status.HTTP_200_OK, content_type='text/plain')


def loader_token(request):
    return HttpResponse(settings.LOADERIO_TOKEN, content_type='text/plain')


class LinksView(APIView):
    permission_classes = (permissions.AllowAny,)
    serializer_class = serializers.Serializer

    def generate_links(self):
        return {}

    def get(self, request, *args, **kwargs):
        links = {
            'links': self.generate_links()
        }

        return Response(links)


class ApiLinksView(LinksView):
    def generate_links(self):
        return {
            'v1': reverse('v1:links', request=self.request),
            'v1.1': reverse('v1.1:links', request=self.request),
            'v2': reverse('v2:links', request=self.request),
        }


class TopLevelApiLinksView(LinksView):
    def generate_links(self):
        links = {
            'instances': reverse('instance-list', request=self.request),
            'backups': reverse('backups', request=self.request),
        }
        if settings.MAIN_LOCATION:
            links.update({
                'account': reverse('account', request=self.request),
                'usage': reverse('stats', request=self.request),
            })
        return links


def exception_handler(exc, context):
    try:
        if 'request' in context:
            # Force reading of POST data
            context['request'].POST
    except Exception as ex:
        exc = ex

    if isinstance(exc, exceptions.APIException) and getattr(exc, 'field', None):
        ret = Response({exc.field: exc.detail},
                       status=exc.status_code,
                       headers=getattr(exc, 'headers', {}))

    # Handle raw Django Validation error as well
    elif isinstance(exc, ValidationError):
        if hasattr(exc, 'message_dict'):
            content = {key: value if isinstance(value, list) else [value]
                       for key, value in exc.message_dict.items()}
        else:
            content = {api_settings.NON_FIELD_ERRORS_KEY: list(exc.messages)}

        ret = Response(content, status=status.HTTP_400_BAD_REQUEST)
    else:
        ret = views.exception_handler(exc, context)

    if ret is not None and not getattr(ret, '_is_rendered', True):
        ret.accepted_renderer = JSONRenderer()
        ret.accepted_media_type = JSONRenderer.media_type
        ret.renderer_context = context
        ret.render()
    return ret
