# coding=UTF8
from rest_framework import status

from apps.core.exceptions import SyncanoException


class InstanceRoleAlreadyExists(SyncanoException):
    status_code = status.HTTP_400_BAD_REQUEST
    field = 'email'
    default_detail = 'Admin with specified Email is already a part of this Instance.'


class InvitationAlreadyExists(SyncanoException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = 'Admin with specified Email already has an invitation created.'
