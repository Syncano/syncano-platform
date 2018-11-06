# coding=UTF8
from rest_framework import status

from apps.core.exceptions import SyncanoException


class InvitationNotFound(SyncanoException):
    status_code = status.HTTP_400_BAD_REQUEST
    field = 'invitation_key'
    default_detail = 'Invitation not found.'


class AdminAlreadyActivated(SyncanoException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = 'Account has already been activated.'
