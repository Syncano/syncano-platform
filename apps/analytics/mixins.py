# coding=UTF8
from django.utils import timezone
from django.utils.dateparse import parse_datetime


class NotifyAdminMixin:
    def get_lock_key(self, email, *args, **kwargs):
        return super().get_lock_key(email)


class NotifyLimitReachedMixin:
    def get_lock_key(self, admin_id, *args, **kwargs):
        return super().get_lock_key(admin_id)


class NotifyAboutPaymentMixin:
    def get_lock_key(self, reference, *args, **kwargs):
        return super().get_lock_key(reference)


class NotifyTimestampMixin:
    def apply_async(self, args=None, kwargs=None, task_id=None, producer=None,
                    link=None, link_error=None, **options):
        kwargs = kwargs or {}
        kwargs['timestamp'] = timezone.now().isoformat()
        return super().apply_async(args, kwargs, task_id, producer, link, link_error,
                                   **options)

    def __call__(self, *args, **kwargs):
        self.timestamp = None
        if 'timestamp' in kwargs:
            self.timestamp = parse_datetime(kwargs.pop('timestamp'))
        self.get_logger().debug('Running with timestamp %s', self.timestamp)
        return super().__call__(*args, **kwargs)
