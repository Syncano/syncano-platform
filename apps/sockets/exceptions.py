# coding=UTF8
from rest_framework import status

from apps.core.exceptions import ObjectProcessingError as _ObjectProcessingError
from apps.core.exceptions import SyncanoException
from apps.sockets.models import Socket


class SocketLocked(SyncanoException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = 'Cannot modify. Please wait until processing has finished.'


class SocketWithUrlRequired(SyncanoException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = 'Cannot update a socket that was not installed from a URL.'


class SocketCountExceeded(SyncanoException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail_fmt = 'Socket count exceeded ({}).'

    def __init__(self, limit):
        detail = self.default_detail_fmt.format(limit)
        super().__init__(detail)


class SocketEnvironmentNotReady(SyncanoException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = 'Socket environment is still processing.'


class SocketEnvironmentFailure(SyncanoException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = 'Socket environment processing failed.'


class ChannelFormatKeyError(SyncanoException):
    status_code = status.HTTP_403_FORBIDDEN
    default_detail = 'Channel format not satisfied.'


class ChannelTooLong(SyncanoException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail_fmt = 'Too long arguments for channel defined. Exceeds max length ({}).'

    def __init__(self, limit):
        detail = self.default_detail_fmt.format(limit)
        super().__init__(detail)


class ObjectProcessingError(_ObjectProcessingError):
    lineno = None
    status = Socket.STATUSES.ERROR

    def __init__(self, message, lineno=None):
        self.lineno = lineno
        super().__init__(message)

    def error_dict(self):
        error_dict = {'error': str(self)}
        if self.lineno:
            error_dict['lineno'] = self.lineno
        return error_dict


class SocketFormattedError(ObjectProcessingError):
    error_prefix = ''
    detail_fmt = None

    def __init__(self, *args, **kwargs):
        message = self.error_prefix + self.detail_fmt.format(*args, **kwargs)
        super().__init__(message)


class SocketMissingFile(SocketFormattedError):
    detail_fmt = 'File not found in zip: "{}".'


class SocketLockedClass(SocketFormattedError):
    detail_fmt = 'Class "{}" is locked.'


class SocketNoDeleteClasses(ObjectProcessingError):
    classes_list_fmt = '\nClasses: "{klasses}" are about to be deleted.'
    class_fields_fmt = '\nFields: "{fields}" of class "{klass}" are about to be deleted.'
    status = Socket.STATUSES.PROMPT

    def __init__(self, classes_list, class_to_fields_dict):
        message = 'Irreversible class changes:'
        if classes_list:
            message += self.classes_list_fmt.format(klasses='", "'.join(classes_list))
        if class_to_fields_dict:
            for klass_name, field_names in class_to_fields_dict.items():
                message += self.class_fields_fmt.format(
                    fields='", "'.join(field_names),
                    klass=klass_name)

        super().__init__(message)


class SocketValidationError(ObjectProcessingError):
    def __init__(self, message, lineno=None):
        super().__init__(message, lineno)


class SocketConfigValidationError(SocketFormattedError):
    error_prefix = 'Error validating socket config. '


class SocketMissingConfigVariable(SocketConfigValidationError):
    detail_fmt = '"{}" is required.'


class SocketConfigWrongFormat(SocketConfigValidationError):
    detail_fmt = 'Wrong format.'
