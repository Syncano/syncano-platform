from rest_framework import status

from apps.core.exceptions import SyncanoException


class UwsgiValueError(SyncanoException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = 'Too big request passed.'
