from django.db import transaction
from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from apps.core.backends.storage import default_storage
from apps.core.helpers import add_post_transaction_success_operation
from apps.data.models import DataObject, Klass
from apps.data.tasks import DeleteKlassIndexesTask, IndexKlassTask
from apps.instances.helpers import get_current_instance
from apps.instances.models import InstanceIndicator


def update_instance_storage_indicator(change):
    if not change:
        return

    instance = get_current_instance()
    indicator_type = InstanceIndicator.TYPES.STORAGE_SIZE

    # Get it first before update as we need to validate limits in post_save signal
    with transaction.atomic():
        indicator = InstanceIndicator.objects.filter(instance=instance, type=indicator_type).select_for_update().get()
        indicator.value += change
        indicator.save()


@receiver(pre_save, sender=DataObject, dispatch_uid='dataobject_pre_save')
def dataobject_pre_save(sender, instance, **kwargs):
    if instance.has_changed('_data'):
        meta = instance._meta
        schema = meta.get_field('_data').schema
        instance.revision += 1

        if schema:
            fields = set([field['source'] for field in schema])
            for key in list(instance._data.keys()):
                if key not in fields:
                    del instance._data[key]

            for key in list(instance._files.keys()):
                if key not in fields:
                    del instance._files[key]


@receiver(post_save, sender=DataObject, dispatch_uid='dataobject_post_save_indicator_update')
def dataobject_post_save_indicator_update(sender, instance, created, **kwargs):
    if instance.is_live:
        old_storage = 0

        if not created:
            old_storage = sum(map(int, instance.old_value('_files').values()))
        new_storage = sum(map(int, instance._files.values()))

        update_instance_storage_indicator(new_storage - old_storage)


@receiver(post_save, sender=DataObject, dispatch_uid='dataobject_post_save_changes')
def dataobject_post_save_changes(sender, instance, created, **kwargs):
    changes = None
    if not created:
        changes = instance.whats_changed(include_virtual=True, skip_fields=('_data',))
    instance.changes = changes


@receiver(post_delete, sender=DataObject, dispatch_uid='dataobject_post_delete_handler')
def dataobject_post_delete_handler(sender, instance, **kwargs):
    for file_source in instance._files.keys():
        file_name = instance._data[file_source]
        default_storage.delete(file_name)
    old_storage = sum(map(int, instance.old_value('_files').values()))
    update_instance_storage_indicator(-old_storage)


# Klass signal handlers

@receiver(post_delete, sender=Klass, dispatch_uid='klass_post_delete_handler')
def klass_post_delete_handler(sender, instance, using, **kwargs):
    add_post_transaction_success_operation(DeleteKlassIndexesTask.delay,
                                           using=using,
                                           instance_pk=get_current_instance().pk,
                                           klass_pk=instance.pk)


@receiver(post_save, sender=Klass, dispatch_uid='klass_post_save_handler')
def klass_post_save_handler(sender, instance, using, **kwargs):
    if instance.index_changes:
        add_post_transaction_success_operation(IndexKlassTask.delay,
                                               using=using,
                                               instance_pk=get_current_instance().pk)
