# coding=UTF8
from django.apps import apps
from django.conf import settings
from django.core.management import call_command
from django.db import router

from apps.core.helpers import get_request_cache


def get_tenant_model():
    return apps.get_model(*settings.TENANT_MODEL.split("."))


def get_public_schema_name():
    return getattr(settings, 'PUBLIC_SCHEMA_NAME', 'public')


def schema_exists(connection, schema_name):
    cursor = connection.cursor()

    # check if this schema already exists in the db
    sql = 'SELECT EXISTS(SELECT 1 FROM pg_catalog.pg_namespace WHERE LOWER(nspname) = LOWER(%s))'
    cursor.execute(sql, (schema_name,))

    row = cursor.fetchone()
    if row:
        exists = row[0]
    else:
        exists = False

    cursor.close()
    return exists


def create_schema(connection, schema_name, check_if_exists=False, sync_schema=True):
    """
    Creates the schema 'schema_name' for this tenant. Optionally checks if the schema
    already exists before creating it. Returns true if the schema was created, false
    otherwise.
    """

    # safety check
    from apps.instances.postgresql_backend.base import _check_identifier

    _check_identifier(schema_name)

    if check_if_exists and schema_exists(connection, schema_name):
        return False

    if sync_schema:
        # migrate will handle schema creation instead
        call_command('migrate',
                     shared=False,
                     schema_name=schema_name,
                     interactive=False,
                     verbosity=getattr(settings, 'SCHEMA_MIGRATIONS_VERBOSITY', 1))
    else:
        cursor = connection.cursor()
        cursor.execute('CREATE SCHEMA "%s"' % schema_name)

    return True


def drop_schema(connection, schema_name):
    # safety check
    from apps.instances.postgresql_backend.base import _check_identifier

    _check_identifier(schema_name)
    cursor = connection.cursor()
    cursor.execute('DROP SCHEMA IF EXISTS "%s" CASCADE' % schema_name)


def rename_schema(connection, old_schema, new_schema):
    # safety check
    from apps.instances.postgresql_backend.base import _check_identifier

    _check_identifier(new_schema)
    cursor = connection.cursor()
    cursor.execute('ALTER SCHEMA "%s" RENAME TO "%s"' % (old_schema, new_schema))


def set_current_instance(tenant):
    get_request_cache().current_tenant = tenant


def get_current_instance():
    return getattr(get_request_cache(), 'current_tenant', None)


def get_instance_db(instance, for_read=False):
    if for_read:
        func = router.db_for_read
    else:
        func = router.db_for_write
    return func(instance.__class__, instance=instance, context='contents')


def get_new_instance_db(instance):
    return router.db_for_write(instance.__class__, instance=instance, context='new')


def is_model_in_tenant_apps(model):
    return apps.get_app_config(model._meta.app_label).name in settings.TENANT_APPS
