# coding=UTF8
from importlib import import_module

from django.conf import settings
from django.db import DatabaseError
from psycopg2 import OperationalError
from retrying import retry

WAIT_BETWEEN_RETRIES = 250
RETRY_COUNT = 10
ORIGINAL_BACKEND = getattr(settings, 'ORIGINAL_BACKEND', 'django.db.backends.postgresql')
original_backend = import_module('.base', ORIGINAL_BACKEND)


class DatabaseWrapper(original_backend.DatabaseWrapper):
    """
    Adds the capability to manipulate statement timeout
    """
    timeout = None
    current_timeout = None

    operators = {
        'exact': '= %s',
        'iexact': 'ILIKE %s',
        'contains': 'LIKE %s',
        'icontains': 'ILIKE %s',
        'regex': '~ %s',
        'iregex': '~* %s',
        'gt': '> %s',
        'gte': '>= %s',
        'lt': '< %s',
        'lte': '<= %s',
        'startswith': 'LIKE %s',
        'endswith': 'LIKE %s',
        'istartswith': 'ILIKE %s',
        'iendswith': 'ILIKE %s',
    }

    pattern_ops = {
        'contains': "LIKE '%%' || {} || '%%'",
        'icontains': "ILIKE '%%' || {} || '%%'",
        'startswith': "LIKE {} || '%%'",
        'istartswith': "ILIKE {} || '%%'",
        'endswith': "LIKE '%%' || {}",
        'iendswith': "ILIKE '%%' || {}",
    }

    def set_timeout(self, timeout):
        self.timeout = timeout

    def set_default_timeout(self):
        self.timeout = None

    def _process_timeout(self, cursor):
        try:
            if self.timeout is not None:
                cursor.execute('SET statement_timeout = {}'.format(self.timeout))
            else:
                cursor.execute('RESET statement_timeout')
        except DatabaseError:
            pass
        self.current_timeout = self.timeout

    @retry(retry_on_exception=lambda x: isinstance(x, OperationalError), wait_fixed=WAIT_BETWEEN_RETRIES,
           stop_max_attempt_number=RETRY_COUNT)
    def get_new_connection(self, conn_params):
        return super().get_new_connection(conn_params)

    def _cursor(self, name=None):
        cursor = None

        if self.current_timeout != self.timeout:
            default_cursor = super()._cursor()
            if name is None:
                cursor = default_cursor
            self._process_timeout(default_cursor)

        if cursor is None:
            cursor = super()._cursor(name)
        return cursor

    def close(self):
        self.current_timeout = None
        super().close()

    def rollback(self):
        self.current_timeout = None
        super().rollback()
