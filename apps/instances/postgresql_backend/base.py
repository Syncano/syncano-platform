# coding=UTF8
import re

from django.db import DEFAULT_DB_ALIAS, DatabaseError

from apps.core.postgresql_backend import base as original_backend
from apps.instances.helpers import get_current_instance, get_public_schema_name
from apps.instances.postgresql_backend.introspection import DatabaseIntrospection

SQL_IDENTIFIER_RE = re.compile(r'^[_\-a-z0-9]{,63}$', re.IGNORECASE)


def _check_identifier(identifier):
    if not SQL_IDENTIFIER_RE.match(identifier):
        raise RuntimeError("Invalid string used for the schema name.")


class DatabaseWrapper(original_backend.DatabaseWrapper):
    """
    Adds the capability to manipulate the search_path using set_tenant and set_schema_name
    """
    _schema_name = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._schema_name = None
        self.introspection = DatabaseIntrospection(self)

    def _process_search_path(self, cursor):
        search_path = self.expected_search_path
        try:
            cursor.execute('SET search_path = "{}","public"'.format(search_path))
            self._schema_name = search_path
        except DatabaseError:
            pass

    @property
    def schema_name(self):
        return self._schema_name or get_public_schema_name()

    @property
    def is_search_path_set(self):
        return self.expected_search_path == self._schema_name

    @property
    def expected_search_path(self):
        search_path = get_public_schema_name()
        instance = get_current_instance()
        if instance:
            search_path = instance.schema_name
        return search_path

    def _cursor(self, name=None):
        """
        Here it happens. We hope every Django db operation using PostgreSQL
        must go through this to get the cursor handle. We change the path.
        """
        # If we're creating a named cursor, process unnamed cursor for search path etc only
        cursor = None

        if self.alias != DEFAULT_DB_ALIAS and not self.is_search_path_set:
            cursor = super()._cursor()
            self._process_search_path(cursor)

        if name is not None or cursor is None:
            cursor = super()._cursor(name)
        return cursor

    def close(self):
        self._schema_name = None
        super().close()

    def rollback(self):
        self._schema_name = None
        super().rollback()
