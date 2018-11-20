# coding=UTF8
from hashlib import md5

from django.conf import settings
from redis.exceptions import LockError

from apps.core.helpers import redis


class TaskLockMixin:
    lock_expire = 15 * 60  # Lock expires in 15 minutes
    lock_generate_hash = False
    lock_blocking_timeout = 0

    def __call__(self, *args, **kwargs):
        logger = self.get_logger()

        lock_key = self.get_lock_key(*args, **kwargs)
        lock_expire = self.get_lock_expire(*args, **kwargs)
        try:
            with redis.lock(lock_key, timeout=lock_expire, blocking_timeout=self.lock_blocking_timeout):
                ret = super().__call__(*args, **kwargs)
            self.after_lock_released(args, kwargs)
            return ret
        except LockError:
            logger.debug('Already locked.')
            return False

    def after_lock_released(self, args, kwargs):
        # Override to add a custom handling when lock gets released
        pass

    def get_lock_key(self, *args, **kwargs):
        lock_key = 'lock:%s' % self.name

        if self.lock_generate_hash:
            key = md5()
            key.update('-'.join((str(a).lower() for a in args)).encode())
            key.update('-'.join(('%s=%s' % (k, kwargs[k]) for k in sorted(kwargs))).encode())
            lock_key = '%s:%s' % (lock_key, key.hexdigest())

        return lock_key

    def get_lock_expire(self, *args, **kwargs):
        return self.lock_expire


class AllowStaffRateThrottleMixin:
    def allow_request(self, request, view):
        if request.user.is_authenticated and request.user.is_staff:
            return True
        return super().allow_request(request, view)


class FastThrottleMixin:
    def allow_request(self, request, view):
        """
        Implement the check to see if the request should be throttled.
        If duration is not 1 second, fallback to default rate limiter.
        """
        if self.duration != 1:
            return super().allow_request(request, view)

        self.key = self.get_cache_key(request, view)
        if self.key is None:
            return True
        self.key = 'throttle:1:{}:{}'.format(int(self.timer()), self.key)

        pipe = redis.pipeline()
        pipe.incr(self.key)
        pipe.expire(self.key, settings.LOCK_TIMEOUT)
        cur_requests, _ = pipe.execute()

        if cur_requests > self.num_requests:
            return self.throttle_failure()
        return self.throttle_success()

    def throttle_success(self):
        if self.duration != 1:
            return super().throttle_success()
        return True

    def wait(self):
        if self.duration != 1:
            return super().throttle_success()
        return 1.0
