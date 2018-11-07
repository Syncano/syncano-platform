# coding=UTF8
from rest_framework import status

from apps.core.exceptions import SyncanoException


class InvalidQuery(SyncanoException):
    status_code = status.HTTP_400_BAD_REQUEST
    field = 'query'
    default_detail = 'Invalid query provided.'


class KlassCountExceeded(SyncanoException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail_fmt = 'Class count exceeded (%d).'

    def __init__(self, limit):
        detail = self.default_detail_fmt % limit
        super().__init__(detail)


class ChannelPublishNotAllowed(SyncanoException):
    status_code = status.HTTP_403_FORBIDDEN
    default_detail = 'You do not have permission to publish data to specified channel.'
