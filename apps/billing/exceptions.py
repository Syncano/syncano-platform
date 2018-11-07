# coding=UTF8
from rest_framework import status

from apps.core.exceptions import SyncanoException


class InvoiceNotReady(Exception):
    pass


class InvalidInvoiceStatus(SyncanoException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = 'Invoice has invalid status.'


class CannotCancelUnpaidSubscription(SyncanoException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = 'Free subscription cannot be cancelled.'


class PaymentFailed(SyncanoException):
    status_code = status.HTTP_400_BAD_REQUEST
    message_format = 'Payment failed: %s'

    def __init__(self, message):
        self.detail = self.message_format % message


class AdminStatusException(SyncanoException):
    status_code = status.HTTP_403_FORBIDDEN
    status = 'error'

    def __init__(self, detail, status):
        self.status = status
        super().__init__(detail=detail)


class StorageLimitReached(SyncanoException):
    status_code = status.HTTP_403_FORBIDDEN
    message = 'Storage limit reached.'


class StripeCardError(SyncanoException):
    status_code = status.HTTP_400_BAD_REQUEST
