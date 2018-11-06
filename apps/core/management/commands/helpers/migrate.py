# coding=UTF8
import io
import os
from importlib import import_module
from threading import local

from django.apps import apps
from django.conf import settings
from django.db.migrations.loader import MigrationLoader
from django.db.migrations.recorder import MigrationRecorder

LOCAL_STORAGE = local()


def get_migration_cache():
    if not hasattr(LOCAL_STORAGE, 'migration_cache'):
        LOCAL_STORAGE.migration_cache = {}
    return LOCAL_STORAGE.migration_cache


def get_migrations(included_apps):
    """
    Get migrations from local cache. If it's not defined in cache yet, run actual implementation.
    """
    if not settings.MIGRATION_CACHE:
        return _get_migrations(included_apps)

    migration_cache = get_migration_cache()
    included_apps_hash = hash(included_apps)

    if included_apps_hash not in migration_cache:
        migration_cache[included_apps_hash] = _get_migrations(included_apps)

    return migration_cache[included_apps_hash]


def _get_migrations(included_apps):
    """
    Get migrations for included apps.
    """
    migration_objects = []

    for app_config in apps.get_app_configs():
        if app_config.name not in included_apps:
            continue
        app_label = app_config.label
        module_name, _ = MigrationLoader.migrations_module(app_label)

        if module_name is None:
            continue

        try:
            module = import_module(module_name)
        except ImportError:
            continue

        directory = os.path.dirname(module.__file__)
        for name in os.listdir(directory):
            if name.endswith(".py"):
                import_name = name.rsplit(".", 1)[0]
                if import_name[0] not in "_.~":
                    migration_objects.append(MigrationRecorder.Migration(app=app_label, name=import_name))
    return migration_objects


def no_migrations_module(cls, app_label):
    return None, True


def ensure_schema(self):
    """
    Ensures the table exists and has the correct schema.
    """
    # If the table's there, that's fine - we've never changed its schema
    # in the codebase.
    cursor = self.connection.cursor()
    cursor.execute(
        """
        SELECT 1
        FROM pg_catalog.pg_class c
        LEFT JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relkind = 'r'
            AND c.relname = %s
            AND n.nspname = %s""", [self.Migration._meta.db_table, self.connection.schema_name])

    if cursor.fetchall():
        return
    # Make the table
    with self.connection.schema_editor() as editor:
        editor.create_model(self.Migration)


def custom_sql_for_model(model, connection):
    # Return output of sql files for models. Used Django 1.8 as a base and simplified a little

    opts = model._meta
    app_dirs = []
    app_dir = apps.get_app_config(model._meta.app_label).path
    app_dirs.append(os.path.normpath(os.path.join(app_dir, 'sql')))

    output = []

    # Find custom SQL, if it's available.
    sql_files = []
    for app_dir in app_dirs:
        sql_files.append(os.path.join(app_dir, "%s.sql" % opts.model_name))
    for sql_file in sql_files:
        if os.path.exists(sql_file):
            with io.open(sql_file, encoding=settings.FILE_CHARSET) as fp:
                output.extend(connection.ops.prepare_sql_script(fp.read()))
    return output
