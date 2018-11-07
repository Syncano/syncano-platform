# coding=UTF8
from rest_framework import status

from apps.core.exceptions import SyncanoException


class BatchLimitExceeded(SyncanoException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail_fmt = 'Max requests per batch exceeded (%d).'

    def __init__(self, limit):
        detail = self.default_detail_fmt % limit
        super().__init__(detail)


class BatchingNotAllowed(SyncanoException):
    status_code = status.HTTP_405_METHOD_NOT_ALLOWED
    default_detail = 'Batching not allowed.'
