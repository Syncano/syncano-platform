# coding=UTF8
from django.template.defaultfilters import filesizeformat
from rest_framework import status

from apps.core.exceptions import SyncanoException


class EmptyBackupException(SyncanoException):
    default_detail = 'Instance no longer exists.'


class SizeLimitExceeded(SyncanoException):
    default_detail_fmt = 'Size limit exceeded ({limit}).'

    def __init__(self, size):
        detail = self.default_detail_fmt.format(limit=filesizeformat(size))
        super().__init__(detail)


class RestoreInstanceNotEmpty(SyncanoException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = 'Cannot restore into non empty instance'


class CannotRestoreIncompleteBackup(SyncanoException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = 'Cannot restore incomplete backup'


class CannotRestoreWithoutTargetInstance(SyncanoException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = 'Cannot restore without target instance'


class CannotRestoreToNonEmptyInstance(SyncanoException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = 'Cannot restore to non empty target instance'


class BackupNotFound(SyncanoException):
    status_code = status.HTTP_404_NOT_FOUND
    default_detail = "Backup not found"


class CannotDeleteActiveBackup(SyncanoException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = 'Cannot delete active backup'


class TooManyBackupsRunning(SyncanoException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = 'You can have only one active backup running.'


class TooManyBackups(SyncanoException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail_fmt = 'Maximum number of backups per account reached ({limit}).'

    def __init__(self, limit):
        detail = self.default_detail_fmt.format(limit=limit)
        super().__init__(detail)
