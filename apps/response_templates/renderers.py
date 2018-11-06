# coding=UTF8
from apps.core.renderers import JSONRenderer
from apps.response_templates.exceptions import TemplateRenderingError


class ResponseTemplatesRenderer(JSONRenderer):
    def render(self, data, accepted_media_type=None, renderer_context=None):
        response = renderer_context['response']
        if response.exception:
            return super().render(data=response.data, renderer_context=renderer_context)

        request = renderer_context['request']
        response_template = request.response_template

        try:
            return response_template.render(request, data=data)
        except TemplateRenderingError as exc:
            response.status_code = exc.status_code
            response._headers['content-type'] = ('Content-Type', 'application/json; charset=utf-8')

            return super().render(data={'detail': exc.detail}, renderer_context=renderer_context)
