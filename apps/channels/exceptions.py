# coding=UTF8
from rest_framework import status

from apps.core.exceptions import SyncanoException


class RoomRequired(SyncanoException):
    status_code = status.HTTP_400_BAD_REQUEST
    field = 'room'
    default_detail = 'This field is required for channels with separate rooms.'


class IncorrectLastId(SyncanoException):
    status_code = status.HTTP_400_BAD_REQUEST
    field = 'last_id'
    default_detail = 'Value is higher than the most current change id.'


class CustomPublishNotAllowed(SyncanoException):
    status_code = status.HTTP_403_FORBIDDEN
    default_detail = 'Custom publish not allowed on this channel.'
