# coding=UTF8
import logging
import traceback
from concurrent import futures

from django.apps import apps
from django.conf import settings
from django.core.management import BaseCommand, CommandError, call_command
from django.core.management.color import no_style
from django.core.management.commands import migrate
from django.db import DEFAULT_DB_ALIAS, connections, transaction
from django.db.migrations.loader import MigrationLoader
from django.db.migrations.recorder import MigrationRecorder
from django.db.models.signals import post_migrate

from apps.core import signals
from apps.core.contextmanagers import ignore_signal
from apps.core.management.commands.helpers import migrate as migrate_helpers
from apps.core.management.commands.helpers.migrate import custom_sql_for_model
from apps.instances.helpers import (
    get_instance_db,
    get_public_schema_name,
    get_tenant_model,
    schema_exists,
    set_current_instance
)

_original_load_disk = MigrationLoader.load_disk
_original_migrations_module = MigrationLoader.migrations_module

MigrationRecorder.ensure_schema = migrate_helpers.ensure_schema


class Command(BaseCommand):
    help = "Migrate schemas"

    def __init__(self, stdout=None, stderr=None, no_color=False):
        self.migrate_command = migrate.Command()
        super().__init__(stdout, stderr, no_color)

    def add_arguments(self, parser):
        parser.add_argument('--tenant', action='store_true', dest='tenant', default=False,
                            help='Tells Django to populate only tenant applications.')
        parser.add_argument('--shared', action='store_true', dest='shared', default=False,
                            help='Tells Django to populate only shared applications.')
        parser.add_argument('--app_label', action='store', dest='app_label', nargs='?',
                            help='App label of an application to synchronize the state.')
        parser.add_argument('--migration_name', action='store', dest='migration_name', nargs='?',
                            help=('Database state will be brought to the state after that '
                                  'migration. Use the name "zero" to unapply all migrations.'))
        parser.add_argument("-s", "--schema", dest="schema_name")
        self.migrate_command.add_arguments(parser)

    def execute(self, *args, **options):
        self.verbosity = int(options.get('verbosity', 1))
        try:
            if self.verbosity == 0:
                logging.disable(logging.INFO)
            super().execute(*args, **options)
        finally:
            logging.disable(logging.NOTSET)

    def handle(self, *args, **options):
        self.db = options.get('database')

        # Don't run migrate during tests on non default database
        if settings.TESTING and self.db != DEFAULT_DB_ALIAS:
            return

        self.sync_tenant = options.get('tenant')
        self.sync_public = options.get('shared')
        self.schema_name = options.get('schema_name')
        self.installed_apps = settings.INSTALLED_APPS
        self.args = args
        self.options = options

        if self.schema_name:
            if self.sync_public:
                raise CommandError("schema should only be used with the --tenant switch.")
            elif self.schema_name == get_public_schema_name():
                self.sync_public = True
            else:
                self.sync_tenant = True
        elif not self.sync_public and not self.sync_tenant:
            # no options set, sync both
            self.sync_tenant = True
            self.sync_public = True

        if hasattr(settings, 'TENANT_APPS'):
            self.tenant_apps = settings.TENANT_APPS
        if hasattr(settings, 'SHARED_APPS'):
            self.shared_apps = settings.SHARED_APPS

        self.process()

    def process(self):
        if self.sync_public and settings.MAIN_LOCATION:
            self.migrate_public_apps()

            self._notice('=== Loading core_data fixtures')
            call_command('loaddata', 'core_data', verbosity=self.verbosity,
                         database=self.db, ignorenonexistent=True)

            config_name = getattr(settings, 'CONFIG_NAME', 'development')
            self._notice('=== Loading %s environment fixtures' % config_name)
            call_command('loaddata', config_name, verbosity=self.verbosity,
                         database=self.db, ignorenonexistent=True)

        if self.sync_tenant:
            self.migrate_tenant_apps(self.schema_name)

        signals.post_full_migrate.send(
            sender=self,
            verbosity=self.verbosity,
            using=self.db)

    def run_migrations(self, connection, included_apps, schema_created=False, skip_checks=False):
        def load_disk(self):
            _original_load_disk(self)
            self.unmigrated_apps = set(
                [app for app in self.unmigrated_apps if apps.get_app_config(app).name in included_apps])
            self.disk_migrations = dict(
                (k, v) for k, v in self.disk_migrations.items() if apps.get_app_config(k[0]).name in included_apps)
            self.ignore_no_migrations = skip_checks

        MigrationLoader.load_disk = load_disk

        # Skip migrations for freshly created schema and process as syncdb instead
        if schema_created:
            MigrationLoader.migrations_module = classmethod(migrate_helpers.no_migrations_module)
        else:
            MigrationLoader.migrations_module = _original_migrations_module

        defaults = self.options.copy()
        defaults['skip_checks'] = skip_checks
        defaults['run_syncdb'] = schema_created or self.options['run_syncdb']
        defaults['database'] = connection.alias
        self.migrate_command.execute(*self.args, **defaults)

        # For fresh schema, populate django_migrations table manually for a much better performance
        if schema_created:
            self._populate_migrations(connection, included_apps)
        # Run custom sql for included apps that have migrations disabled or when new schema was created
        self._run_custom_sql(connection, included_apps, force=schema_created)

    def migrate_tenant_apps(self, schema_name=None):
        apps = self.tenant_apps or self.installed_apps
        tenants = get_tenant_model().objects.filter(location=settings.LOCATION)

        if schema_name:
            tenants = tenants.filter(schema_name=schema_name)

        if not tenants.exists():
            self._notice("No tenants found")
            return

        if schema_name:
            # Only one tenant to migrate
            self._migrate_tenants(tenants, apps)
            return

        min_id = tenants.first().id
        max_id = tenants.last().id
        future_list = []

        with futures.ThreadPoolExecutor(max_workers=settings.CONCURRENT_MIGRATION_THREADS) as executor:
            while min_id <= max_id:
                future = executor.submit(self._migrate_tenants,
                                         tenants.filter(id__gte=min_id, id__lt=min_id + 100),
                                         apps)
                future_list.append(future)
                min_id += 100

        # Wait for all results. Raises exception if any was raised in future
        for f in futures.as_completed(future_list):
            f.result()

    def migrate_public_apps(self):
        apps = self.shared_apps or self.installed_apps
        self._notice("=== Running migrate for schema: public")
        self.run_migrations(connections[self.db], apps)

    def _migrate_schema(self, connection, tenant):
        created = False
        if not schema_exists(connection, tenant.schema_name):
            connection.cursor().execute('CREATE SCHEMA "%s"' % tenant.schema_name)
            created = True
        MigrationRecorder(connection).ensure_schema()
        return created

    def _migrate_tenants(self, tenants, apps):
        for tenant in tenants:
            db = get_instance_db(tenant)
            connection = connections[db]
            set_current_instance(tenant)

            self._notice("=== Running migrate for schema: %s" % tenant.schema_name)
            signals.pre_tenant_migrate.send(
                sender=tenant,
                tenant=tenant,
                verbosity=self.verbosity,
                using=connection.alias)
            schema_created = self._migrate_schema(connection, tenant)

            with ignore_signal(post_migrate):
                self.run_migrations(connection, apps, schema_created=schema_created, skip_checks=True)

            signals.post_tenant_migrate.send(
                sender=tenant,
                tenant=tenant,
                verbosity=self.verbosity,
                using=connection.alias,
                created=schema_created,
                partial=False,
            )

    def _populate_migrations(self, connection, included_apps):
        MigrationLoader.migrations_module = _original_migrations_module
        migration_objects = migrate_helpers.get_migrations(included_apps)
        MigrationRecorder(connection).migration_qs.bulk_create(migration_objects)

        # Reset sequences
        statements = connection.ops.sequence_reset_sql(no_style(), (MigrationRecorder.Migration,))
        with connection.cursor() as cursor:
            for line in statements:
                cursor.execute(line)

    def _run_custom_sql(self, connection, included_apps, force=False):
        self._notice("  Installing custom SQL...\n")
        cursor = connection.cursor()

        for app_config in apps.get_app_configs():
            app_name = app_config.name

            # Skip apps that are not included
            if app_name not in included_apps or (
                    # or are either not forced and do not have migrations disabled
                    not force and (app_config.label not in settings.MIGRATION_MODULES or
                                   settings.MIGRATION_MODULES[app_config.label] != 'notmigrations')
            ):
                continue

            for model in app_config.get_models():
                custom_sql = custom_sql_for_model(model, connection)
                if custom_sql:
                    if self.verbosity >= 2:
                        self.stdout.write(
                            "    Installing custom SQL for %s.%s model\n" %
                            (app_config, model._meta.object_name)
                        )
                    try:
                        with transaction.atomic(using=connection.alias):
                            for sql in custom_sql:
                                cursor.execute(sql)
                    except Exception as e:
                        self.stderr.write(
                            "    Failed to install custom SQL for %s.%s model: %s\n"
                            % (app_name, model._meta.object_name, e)
                        )
                        traceback.print_exc()
                else:
                    if self.verbosity >= 3:
                        self.stdout.write(
                            "    No custom SQL for %s.%s model\n" %
                            (app_name, model._meta.object_name)
                        )

    def _notice(self, output):
        if int(self.options.get('verbosity', 1)) >= 1:
            self.stdout.write(self.style.NOTICE(output))
