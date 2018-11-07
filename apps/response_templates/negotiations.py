# coding=UTF8
from rest_framework.exceptions import NotAcceptable
from rest_framework.negotiation import DefaultContentNegotiation

from apps.core.helpers import Cached
from apps.response_templates.models import ResponseTemplate
from apps.response_templates.renderers import ResponseTemplatesRenderer


class ResponseTemplateNegotiation(DefaultContentNegotiation):

    def select_renderer(self, request, renderers, format_suffix=None):
        template_name = ResponseTemplate.get_name_from_request(request)
        if template_name and getattr(request, 'instance', None) is not None:
            try:
                request.response_template = Cached(ResponseTemplate, kwargs={'name': template_name}).get()
            except ResponseTemplate.DoesNotExist:
                raise NotAcceptable
            renderer = ResponseTemplatesRenderer()
            renderer.media_type = request.response_template.content_type
            return renderer, renderer.media_type
        return super().select_renderer(request, renderers, format_suffix)
