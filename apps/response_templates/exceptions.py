# coding=UTF8
from rest_framework import status

from apps.core.exceptions import SyncanoException


class UnsafePropertiesOnTemplate(SyncanoException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = 'Access unsafe properties in a template is forbidden.'


class Jinja2TemplateRenderingError(SyncanoException):
    status_code = status.HTTP_400_BAD_REQUEST

    message_format = 'Template rendering failed: {message}'

    def __init__(self, message):
        self.detail = self.message_format.format(message=message)


class TemplateRenderingTimeout(SyncanoException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = 'Template rendering timeout'


class TemplateRenderingError(SyncanoException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = 'Template rendering failed'
