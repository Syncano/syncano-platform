# coding=UTF8
import functools

from apps.batch.exceptions import BatchingNotAllowed


def disallow_batching(f):
    """
    Used to disallow including that endpoint in batching requests.
    """

    @functools.wraps(f)
    def outer(self, request, *args, **kwargs):
        if request.META.get('X_BATCHING', '') == '1':
            raise BatchingNotAllowed()
        return f(self, request, *args, **kwargs)

    return outer
