# coding=UTF8
import rapidjson as json
from django.conf import settings
from rest_framework.exceptions import ParseError
from rest_framework.parsers import BaseParser
from rest_framework.parsers import FormParser as _FormParser
from rest_framework.parsers import MultiPartParser as _MultiPartParser
from rest_framework.renderers import JSONRenderer


class BaseJSONParser(BaseParser):
    """
    Parses JSON-serialized data by rapidjson parser.
    """

    media_type = 'application/json'
    renderer_class = JSONRenderer

    def parse(self, stream, media_type=None, parser_context=None):
        """
        Parses the incoming bytestream as JSON and returns the resulting data.
        """
        parser_context = parser_context or {}
        encoding = parser_context.get('encoding', settings.DEFAULT_CHARSET)

        try:
            data = stream.read().decode(encoding)
            return json.loads(data)
        except ValueError as exc:
            raise ParseError('JSON parse error - %s' % str(exc))


class ParserMixin:
    """
    Do not process stream twice in nested calls.
    If stream was already parsed, return it.
    """

    def parse(self, stream, media_type=None, parser_context=None):
        if hasattr(stream, 'data'):
            return stream.data

        return super().parse(stream, media_type, parser_context)


class JSONParser(ParserMixin, BaseJSONParser):
    pass


class FormParser(ParserMixin, _FormParser):
    pass


class MultiPartParser(ParserMixin, _MultiPartParser):
    pass
