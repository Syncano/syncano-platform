# coding=UTF8
import functools
from datetime import datetime

import psycopg2
from django.conf import settings
from django.db import OperationalError, connections, router
from psycopg2._psycopg import QueryCanceledError

from apps.core.exceptions import QueryTimeout
from apps.core.helpers import Cached


# CACHE
def cached(method=None, timeout=None):
    if method is None:
        return functools.partial(cached, timeout=timeout)

    @functools.wraps(method)
    def f(*args, **kwargs):
        return Cached(method, args=args, kwargs=kwargs, timeout=timeout).get()

    def invalidate(args=(), kwargs=None, immediate=None):
        Cached(method, args=args, kwargs=kwargs, timeout=timeout).invalidate(immediate=immediate)

    f.invalidate = invalidate
    return f


def sql_timeout(model, count):
    def outer(f):
        @functools.wraps(f)
        def wrapped(*args, **kwargs):
            db = router.db_for_read(model)
            connection = connections[db]
            start = datetime.now()
            try:
                connection.set_timeout(settings.DATA_OBJECT_STATEMENT_TIMEOUT)
                return f(*args, **kwargs)
            except QueryCanceledError:
                raise QueryTimeout()
            except (OperationalError, psycopg2.OperationalError):
                # Make sure we are dealing with timeout
                if (datetime.now() - start).total_seconds() * 1000 > settings.DATA_OBJECT_STATEMENT_TIMEOUT:
                    raise QueryTimeout()
                raise
            finally:
                connection.set_default_timeout()

        return wrapped

    return outer


def disable_during_tests(f):
    """Decorated function will not be invoked during tests."""

    @functools.wraps(f)
    def outer(*args, **kwargs):
        if settings.TESTING:
            return
        return f(*args, **kwargs)

    return outer


def force_atomic(enabled):
    """
    Used to force enable or disable atomic behavior for endpoint.
    """
    def wrapped(func):
        func.force_atomic = enabled
        return func
    return wrapped
