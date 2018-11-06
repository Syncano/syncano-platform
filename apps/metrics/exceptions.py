# coding=UTF8
from rest_framework import status

from apps.core.exceptions import SyncanoException


class IncorrectQueryValue(SyncanoException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = 'Incorrect value.'
