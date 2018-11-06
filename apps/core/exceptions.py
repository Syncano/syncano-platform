# coding=UTF8
from rest_framework import status
from rest_framework.exceptions import APIException


class ObjectProcessingError(Exception):
    retry = False


class SyncanoException(APIException):
    default_detail = ''

    def __init__(self, detail=None, field=None):
        super().__init__(detail)
        if field is not None:
            self.field = field


class PermissionDenied(SyncanoException):
    status_code = status.HTTP_403_FORBIDDEN
    default_detail = 'You do not have permission to perform this action.'


class AdminNotFound(SyncanoException):
    status_code = status.HTTP_401_UNAUTHORIZED
    default_detail = 'Invalid email.'


class UserNotFound(SyncanoException):
    status_code = status.HTTP_401_UNAUTHORIZED
    default_detail = 'Invalid username.'


class WrongPassword(SyncanoException):
    status_code = status.HTTP_401_UNAUTHORIZED
    default_detail = 'Invalid password.'


class WrongTokenCredentials(SyncanoException):
    status_code = status.HTTP_401_UNAUTHORIZED
    default_detail = 'Invalid authorization token.'


class UnsupportedSocialBackend(SyncanoException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = 'Unsupported social backend.'


class InvalidSocialScopeMissingEmail(SyncanoException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = 'Invalid social scope, missing email.'


class LimitReached(SyncanoException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = 'Too much data provided.'


class MalformedPageParameter(SyncanoException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = 'Incorrect page parameter provided.'


class OrderByIncorrect(SyncanoException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = 'Incorrect order_by parameter provided.'


class QueryTimeout(SyncanoException):
    status_code = status.HTTP_408_REQUEST_TIMEOUT
    default_detail = 'Requested query took too long. Timeout was reached.'


class RequestTimeout(SyncanoException):
    status_code = status.HTTP_408_REQUEST_TIMEOUT
    default_detail = 'Request timeout.'


class ModelNotFound(SyncanoException):
    status_code = status.HTTP_404_NOT_FOUND

    def __init__(self, model):
        name = model._meta.verbose_name
        self.detail = '%s%s was not found.' % (name[0].upper(), name[1:])


class CodeMissing(SyncanoException):
    status_code = status.HTTP_400_BAD_REQUEST
    field = 'code'
    default_detail = 'Code was not created.'


class StateMissing(SyncanoException):
    status_code = status.HTTP_400_BAD_REQUEST
    field = 'state'
    default_detail = 'State is missing.'


class RevisionMismatch(SyncanoException):
    status_code = status.HTTP_400_BAD_REQUEST
    field = 'expected_revision'

    def __init__(self, current, expected):
        self.detail = 'Revision mismatch. Expected {expected}, got {current}.'.format(current=current,
                                                                                      expected=expected)


class RequestLimitExceeded(SyncanoException):
    status_code = status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
    default_detail_fmt = 'Request size limit exceeded (%d).'

    def __init__(self, limit):
        detail = self.default_detail_fmt % limit
        super().__init__(detail)
