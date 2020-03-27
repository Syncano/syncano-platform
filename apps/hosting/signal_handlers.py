# coding=UTF8
from django.db import transaction
from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from apps.core.helpers import add_post_transaction_success_operation
from apps.data.signal_handlers import update_instance_storage_indicator
from apps.hosting.helpers import add_domains_to_syncano_instance, remove_domains_from_syncano_instance
from apps.hosting.models import Hosting, HostingFile
from apps.instances.helpers import get_current_instance
from apps.instances.models import Instance

from .tasks import HostingAddSecureCustomDomainTask


@receiver(post_delete, sender=HostingFile, dispatch_uid='hosting_file_post_delete_handler')
def hosting_file_post_delete_handler(sender, instance, **kwargs):
    instance.file_object.delete(save=False)
    update_instance_storage_indicator(-instance.size)


@receiver(pre_save, sender=Hosting, dispatch_uid='hosting_pre_save_handler')
def hosting_pre_save_handler(sender, instance, **kwargs):
    # If we are soft deleting hosting object - clear domains for cleanup in post_save
    if not instance.is_live:
        instance.domains = []
        instance.ssl_status = Hosting.SSL_STATUSES.OFF
        return

    if not Hosting.objects.exists():
        instance.is_default = True

    # Return if we are already running a check for SSL
    if instance.ssl_status == Hosting.SSL_STATUSES.CHECKING:
        return

    # If CNAME has changed or wasn't provided before - check for ssl status,
    # otherwise if there is no cname now, turn it off
    if instance.has_changed('domains'):
        old_cname = instance.old_value('domains')
    elif instance.id is None:
        old_cname = None
    else:
        return

    new_cname = instance.get_cname()
    if not new_cname:
        instance.ssl_status = Hosting.SSL_STATUSES.OFF
    elif old_cname != new_cname:
        instance.ssl_status = Hosting.SSL_STATUSES.CHECKING


@receiver(post_save, sender=Hosting, dispatch_uid='hosting_post_save_handler')
def hosting_post_save_handler(sender, instance, created, using, **kwargs):
    syncano_instance_pk = get_current_instance().pk
    new_cname = Hosting.find_cname(instance.domains)
    if created:
        old_cname = None
    else:
        old_cname = Hosting.find_cname(instance.old_value('domains'))

    if new_cname != old_cname:
        with transaction.atomic():
            syncano_instance = Instance.objects.select_for_update().get(pk=syncano_instance_pk)
            if new_cname is not None:
                add_domains_to_syncano_instance(syncano_instance, domains=[new_cname])
            if old_cname is not None:
                remove_domains_from_syncano_instance(syncano_instance, domains=[old_cname])
            syncano_instance.save(update_fields=['domains'])

    if instance.ssl_status == Hosting.SSL_STATUSES.CHECKING:
        add_post_transaction_success_operation(
            HostingAddSecureCustomDomainTask.delay,
            using=using,
            hosting_pk=instance.id,
            hosting_name=instance.name,
            domain=instance.get_cname(),
            instance_pk=syncano_instance_pk,
        )


@receiver(post_save, sender=HostingFile, dispatch_uid='hostingfile_post_save_handler')
def hostingfile_post_save_handler(sender, instance, created, **kwargs):
    # Invalidate cached check if hosting is empty
    Hosting.is_hosting_empty.invalidate(args=(instance.hosting_id,), immediate=False)
    # Invalidate hosting file.
    HostingFile.invalidate_file(hosting_id=instance.hosting_id, path=instance.path)

    if instance.is_live and instance.file_object:
        # Update instance storage size
        old_storage = 0

        if not created:
            old_storage = instance.old_value('size')
        new_storage = instance.size

        update_instance_storage_indicator(new_storage - old_storage)
