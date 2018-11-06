# coding=UTF8
from rest_framework import status

from apps.core.exceptions import SyncanoException


class InstanceCountExceeded(SyncanoException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail_fmt = 'Instance count exceeded (%d).'

    def __init__(self, limit):
        detail = self.default_detail_fmt % limit
        super().__init__(detail)


class InstanceVersionMismatch(SyncanoException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = 'Instance version mismatch. Not compatible with used API version.'


class InstanceLocationMismatch(SyncanoException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = 'Instance was created in different location. Use relevant API endpoint.'
