# coding=UTF8
from hashlib import md5

from django.conf import settings

from apps.core.helpers import redis


class TaskLockMixin:
    lock_expire = 15 * 60  # Lock expires in 15 minutes
    lock_generate_hash = False
    lock_blocking_timeout = 0

    def __call__(self, *args, **kwargs):
        logger = self.get_logger()
        self.lock = None
        self.lock_acquired = False

        logger.debug('Acquiring lock...')
        if not self.acquire_lock(*args, **kwargs):
            logger.debug('Already locked.')
            return False

        self.lock_acquired = True
        logger.debug('Lock aquired.')
        return super().__call__(*args, **kwargs)

    def acquire_lock(self, *args, **kwargs):
        if not self.lock:
            lock_key = self.get_lock_key(*args, **kwargs)
            lock_expire = self.get_lock_expire(*args, **kwargs)
            self.lock = redis.lock(lock_key, timeout=lock_expire, blocking_timeout=self.lock_blocking_timeout)
        if not self.lock_acquired:
            self.lock_acquired = self.lock.acquire()
        return self.lock_acquired

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

    def after_return(self, status, retval, task_id, args, kwargs, einfo):
        if self.lock_acquired:
            try:
                self.lock.release()
                self.after_lock_released(args, kwargs)
            except Exception:
                self.get_logger().exception('Unexpected exception during releasing lock.')
        super().after_return(status, retval, task_id, args, kwargs, einfo)


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
