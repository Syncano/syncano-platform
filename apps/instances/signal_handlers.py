from django.conf import settings
from django.core.management import call_command
from django.db import connections
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from apps.core.signals import post_full_migrate
from apps.core.tasks import DeleteFilesTask
from apps.instances.helpers import drop_schema, get_instance_db
from apps.instances.models import Instance, InstanceIndicator


@receiver(post_delete, sender=Instance, dispatch_uid='instance_post_delete_handler')
def instance_post_delete_handler(sender, instance, **kwargs):
    db = get_instance_db(instance)
    drop_schema(connections[db], schema_name=instance.schema_name)
    DeleteFilesTask.delay(instance.get_storage_prefix(), all_buckets=True)


@receiver(post_save, sender=Instance, dispatch_uid='instance_post_save_handler')
def instance_post_save_handler(sender, instance, created, **kwargs):
    if created:
        InstanceIndicator.objects.create(instance=instance, type=InstanceIndicator.TYPES.APNS_DEVICES_COUNT)
        InstanceIndicator.objects.create(instance=instance, type=InstanceIndicator.TYPES.SCHEDULES_COUNT)
        InstanceIndicator.objects.create(instance=instance, type=InstanceIndicator.TYPES.STORAGE_SIZE)


@receiver(post_full_migrate)
def instances_post_migrate_handler(sender, verbosity, using, **kwargs):
    # Migrate only when not testing and first instance does not exist
    if not settings.TESTING and not Instance.objects.filter(pk=1).exists():
        # Create default instance along with admin user with password="default" and default API key
        call_command('loaddata', 'init_instances', verbosity=verbosity,
                     database=using)
        call_command('migrate',
                     shared=False,
                     tenant=True,
                     interactive=False,
                     verbosity=0)
