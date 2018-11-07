# coding=UTF8
from apps.core.parsers import BaseJSONParser


class PreflightParser(BaseJSONParser):

    media_type = 'text/plain'
    valid_methods = {'GET', 'POST', 'PUT', 'PATCH', 'DELETE'}

    def parse(self, stream, media_type=None, parser_context=None):
        if hasattr(stream, 'data'):
            # If stream was already parsed, just return it.
            return stream.data

        data = super().parse(stream, media_type, parser_context)

        request = parser_context['request']
        view = parser_context['view']
        if request.method == 'POST' and isinstance(data, dict) \
                and '_method' in data and data['_method'] in self.valid_methods:
            request.method = data['_method']
            action_map = getattr(view, 'action_map', {})
            view.action = action_map.get(request.method.lower())

        return data
