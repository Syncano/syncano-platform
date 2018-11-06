# coding=UTF8
from django.conf import settings
from rest_framework import status

from apps.core.exceptions import SyncanoException


class UserGroupCountExceeded(SyncanoException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "User's group count exceeded (%d)." % settings.USER_GROUP_MAX_COUNT


class MembershipAlreadyExists(SyncanoException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = 'User is already a part of that group.'
