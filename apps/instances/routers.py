# coding=UTF8
from django.conf import settings
from django.db import DEFAULT_DB_ALIAS

from apps.instances.helpers import get_current_instance, get_instance_db, get_tenant_model, is_model_in_tenant_apps

INSTANCES_DB_ALIAS = getattr(settings, 'INSTANCES_DB_ALIAS', 'instances')
INSTANCES_NEW_DB_ALIAS = getattr(settings, 'INSTANCES_NEW_DB_ALIAS', 'instances')


class InstanceRouter:
    TENANT_MODEL = get_tenant_model()

    def db_for_model(self, model, for_read=False, instance=None, context=None, **hints):
        if model is self.TENANT_MODEL:
            if context == 'new':
                return INSTANCES_NEW_DB_ALIAS
            if context == 'contents':
                # As instance objects are cached, temporarily use getattr so it works
                # with objects that miss that field
                return instance.database or INSTANCES_DB_ALIAS

        elif is_model_in_tenant_apps(model):
            return get_instance_db(get_current_instance(), for_read=for_read)
        return DEFAULT_DB_ALIAS

    def db_for_write(self, model, **hints):
        return self.db_for_model(model, **hints)

    def db_for_read(self, model, **hints):
        return self.db_for_model(model, for_read=True, **hints)
