# coding=UTF8
from rest_framework import status

from apps.core.exceptions import SyncanoException

from .models import Hosting


class PathAlreadyExists(SyncanoException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = 'This field must be unique.'
    field = 'path'


class OnlyOneDomainAllowed(SyncanoException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = 'Only one fully qualified domain per hosting.'


class ValidCNameMissing(SyncanoException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = 'Domains must contain a valid domain entry.'


class HostingLocked(SyncanoException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = 'Cannot modify hosting. Please wait until SSL check process has finished.'


class HostingDomainException(SyncanoException):
    status_code = status.HTTP_400_BAD_REQUEST
    status = Hosting.SSL_STATUSES.UNKNOWN


class DomainAlreadyUsed(HostingDomainException):
    status = Hosting.SSL_STATUSES.WRONG_CNAME
    default_detail = 'Domain already used.'


class WrongCName(HostingDomainException):
    status = Hosting.SSL_STATUSES.WRONG_CNAME
    default_detail = 'CNAME must point to your hosting instance.'


class CNameNotSet(HostingDomainException):
    status = Hosting.SSL_STATUSES.CNAME_NOT_SET
    default_detail = 'CNAME is not set for domain name.'


class DomainDoesNotExist(HostingDomainException):
    status = Hosting.SSL_STATUSES.INVALID_DOMAIN
    default_detail = 'Domain name can not be resolved.'
