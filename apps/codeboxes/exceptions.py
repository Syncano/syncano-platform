from rest_framework import status

from apps.core.exceptions import SyncanoException


class DockerImageCannotBePulled(Exception):
    pass


class CodeBoxScheduleAlreadyRunning(Exception):
    pass


class ContainerException(Exception):
    pass


class CannotCreateContainer(ContainerException):
    pass


class CannotCleanupContainer(ContainerException):
    pass


class CannotStartContainer(ContainerException):
    pass


class CannotExecContainer(ContainerException):
    pass


class ScriptWrapperError(ContainerException):
    pass


class ScheduleCountExceeded(SyncanoException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail_fmt = 'Schedule count exceeded (%d).'

    def __init__(self, limit):
        detail = self.default_detail_fmt % limit
        super().__init__(detail)


class LegacyCodeBoxDisabled(SyncanoException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail_fmt = 'Legacy CodeBoxes are disabled, use Sockets.'
