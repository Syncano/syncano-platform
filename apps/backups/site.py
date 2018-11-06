from logging import getLogger

from django.conf import settings
from django.core.exceptions import FieldDoesNotExist, FieldError, ValidationError
from django.core.management import call_command
from django.core.management.color import no_style
from django.db import connections, transaction
from django.db.migrations.topological_sort import topological_sort_as_sets
from django.db.models.base import ModelBase
from django.utils.functional import cached_property

from apps.core import signals
from apps.core.helpers import generate_key
from apps.instances.contextmanagers import instance_context
from apps.instances.helpers import get_instance_db

from .options import ModelBackup

logger = getLogger(__name__)


class BackupSite:
    MIGRATIONS_STORAGE = 'migrations'

    def __init__(self):
        self._registry = {}
        self.apps = set()
        self.models = set()

    def register(self, model_or_iterable, backup_class=None):
        if backup_class is None:
            backup_class = ModelBackup
        if isinstance(model_or_iterable, ModelBase):
            model_or_iterable = [model_or_iterable]

        for model in model_or_iterable:
            model_label = model._meta.label
            if model_label in self._registry:
                raise RuntimeError('Model %s is already registered for backup.' % model.__name__)
            self._registry[model_label] = backup_class
            self.models.add(model)
            self.apps.add(model._meta.app_label)

    def get_model_dependencies(self, model):
        deps = set()
        for field in model._meta.local_fields:
            if getattr(field, 'many_to_one', False) or getattr(field, 'one_to_one', False):
                if field.related_model != model:
                    deps.add(field.related_model._meta.label)
        return deps

    @cached_property
    def default_sorted(self):
        return self.calculate_sorted()

    def calculate_sorted(self, apps=None):
        if apps is not None:
            models = set()
            for model_map in apps.all_models.values():
                for model in model_map.values():
                    # Only process models that are in backup registry
                    if model._meta.label in self._registry:
                        models.add(model)
        else:
            models = self.models

        models_by_label = {model._meta.label: model for model in models}
        out = []
        dependency_graph = {model._meta.label: self.get_model_dependencies(model)
                            for model in models}
        for group in topological_sort_as_sets(dependency_graph):
            group = {models_by_label[l] for l in group}
            out += sorted(group, key=lambda mdl: mdl.__name__)
        return out

    def backup_instance(self, storage, instance, query_args=None):
        """ query_args is a dict in a form of
        {
            'model_backup_name': [id_list],
            'model_backup_name3': [], #no data
        }
        If there is no key in query_args, queryset is not filtered
        """
        with instance_context(instance):
            db = get_instance_db(instance)

            # get migrations
            targets = self.get_instance_migrations(instance)
            storage.start_model(self.MIGRATIONS_STORAGE)
            for target in targets:
                storage.append(target)
            storage.end_model()

            with transaction.atomic(using=db):
                cursor = transaction.get_connection(db).cursor()
                cursor.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ;')
                for model in self.default_sorted:
                    options = self.get_options_for_model(model)
                    storage.start_model(options.get_name())
                    try:
                        options.backup(storage, query_args)
                    except Exception:
                        logger.warning('Exception for model %s', model, exc_info=1)
                        raise
                    storage.end_model()

    def get_instance_migrations(self, instance):
        from django.db.migrations.loader import MigrationLoader
        db = get_instance_db(instance)
        with instance_context(instance):
            targets = [target
                       for target in MigrationLoader(connections[db]).graph.leaf_nodes()
                       if target[0] in self.apps]
        return targets

    def get_options_for_model(self, model):
        backup_class = self._registry[model._meta.label]
        return backup_class(model, self)

    def get_stored_migration_targets(self, storage):
        # for each app get latest applied migration
        targets = {}
        for target in storage.get_model_storage(self.MIGRATIONS_STORAGE):
            app, migration_name = target
            # If app is not in registered models skip it
            if app not in self.apps:
                continue
            if app not in targets or targets[app] < migration_name:
                targets[app] = migration_name
        return targets.items()

    @transaction.atomic
    def restore_to_new_schema(self, storage, instance, partial=False):
        from apps.instances.models import Instance
        from .executor import BackupMigrationExecutor

        db = get_instance_db(instance)
        con = connections[db]

        stored_targets = self.get_stored_migration_targets(storage)

        new_instance = Instance(owner=instance.owner,
                                name="_%s" % generate_key(),
                                schema_name="%s_{self.id}_%s" % (instance.id, instance.name),
                                database=instance.database)

        # If there are no stored migrations sync_schema on create
        try:
            new_instance.save(sync_schema=not stored_targets)
            new_instance.storage_prefix = "%s_%s" % (instance.pk, new_instance.pk)
            new_instance.save()

            apps = None
            if stored_targets:
                with instance_context(new_instance):
                    executor = BackupMigrationExecutor(con)
                    state = executor.migrate(stored_targets)
                    apps = state.apps

                    if partial:
                        signals.post_tenant_migrate.send(
                            sender=new_instance,
                            tenant=new_instance,
                            using=con.alias,
                            created=True,
                            partial=True,
                        )

            models_sorted = self.calculate_sorted(apps)
            self.restore_to_instance(storage, new_instance, models_sorted, apps, partial=partial)

            # Upgrade schema to current version
            # migrate will detect that this instance is already created
            # and will forward to current project state
            # it will not fire post_migrate signals
            # and it will fire post_tenant_migrate with schema_created=False
            # Initial data will be fed from migrations (a common way how we do it in project)
            if stored_targets:
                call_command('migrate',
                             shared=False,
                             schema_name=new_instance.schema_name,
                             interactive=False,
                             verbosity=settings.SCHEMA_MIGRATIONS_VERBOSITY)

            # swap prefixes. When new_instance is deleted, old instance files will also be deleted.
            instance.storage_prefix, new_instance.storage_prefix = (new_instance.get_storage_prefix(),
                                                                    instance.get_storage_prefix())
            # swap schemas
            instance.schema_name, new_instance.schema_name = (new_instance.schema_name, instance.schema_name)
            instance.save()
            new_instance.save()
        finally:
            new_instance.delete()

    def truncate_models(self, connection, models):
        tables = [model._meta.db_table for model in models]

        statements = connection.ops.sql_flush(no_style(), tables, [], True)
        with connection.cursor() as cursor:
            for line in statements:
                cursor.execute(line)

    def reset_sequences(self, connection, models):
        statements = connection.ops.sequence_reset_sql(no_style(), models)
        with connection.cursor() as cursor:
            for line in statements:
                cursor.execute(line)

    def restore_to_instance(self, storage, instance, models_sorted, apps=None, partial=False):
        db = get_instance_db(instance)
        connection = connections[db]

        with instance_context(instance), transaction.atomic(using=db):
            if not partial:
                self.truncate_models(connection, models_sorted)

            for model in models_sorted:
                self.get_options_for_model(model).restore(storage, partial)

            self.reset_sequences(connection, models_sorted)

    @cached_property
    def jsonschema(self):
        schema = {'type': 'object',
                  'properties': {},
                  'additionalProperties': False}
        for model in self.default_sorted:
            opt = self.get_options_for_model(model)
            if opt.lookup_field == 'id':
                id_type = 'integer'
            else:
                id_type = 'string'

            model_schema = {'anyOf': [
                            {'type': 'null'},
                            {'type': 'array', 'items': {'type': id_type}}
                            ]}
            schema['properties'][opt.get_name()] = model_schema
        return schema

    def validate_query_args(self, query_args):
        try:
            for model in self.default_sorted:
                opts = self.get_options_for_model(model)
                opts.get_queryset(query_args)
        except (FieldError, FieldDoesNotExist) as e:
            raise ValidationError(e)


default_site = BackupSite()
register = default_site.register
