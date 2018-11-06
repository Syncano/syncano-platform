# coding=UTF8
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.core.abstract_models import LiveAbstractModel
from apps.instances.contextmanagers import instance_context
from apps.instances.helpers import get_instance_db, is_model_in_tenant_apps
from apps.instances.models import Instance


class Command(BaseCommand):
    help = 'Delete dead objects. ' \
           'Note that this should not be needed normally and it will generate a lot of queries ' \
           'when used on production.'

    def _notice(self, output):
        if self.verbosity > 0:
            self.stdout.write(self.style.NOTICE(output))  # pragma: no cover

    def handle(self, *args, **options):
        self.verbosity = int(options.get('verbosity'))

        tenant_models = []
        self._notice('* Processing global models.')

        for subclass in LiveAbstractModel.__subclasses__():
            if is_model_in_tenant_apps(subclass):
                tenant_models.append(subclass)
            else:
                # Process common subclasses
                with transaction.atomic():
                    self._notice('- Deleting objects from model %s.' % subclass._meta.object_name)
                    subclass.all_objects.dead().delete()

        # Process instanced data
        for instance in Instance.objects.iterator():
            self._notice('* Processing models from instance: %s.' % instance.name)

            with instance_context(instance):
                db = get_instance_db(instance)
                for tenant_model in tenant_models:
                    with transaction.atomic(db):
                        self._notice('- Deleting objects from model %s.' % tenant_model._meta.object_name)
                        tenant_model.all_objects.dead().delete()
