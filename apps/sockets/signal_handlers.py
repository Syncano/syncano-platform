# coding=UTF8

from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from apps.core.helpers import add_post_transaction_success_operation
from apps.core.tasks import DeleteFilesTask
from apps.instances.helpers import get_current_instance
from apps.sockets.helpers import unref_data_klass
from apps.sockets.models import Socket, SocketEnvironment
from apps.sockets.processor import ClassDependency
from apps.sockets.tasks import SocketCheckerTask, SocketEnvironmentProcessorTask, SocketProcessorTask


@receiver(pre_save, sender=Socket, dispatch_uid='socket_pre_save_handler')
def socket_pre_save_handler(sender, instance, using, **kwargs):
    if instance.is_live and instance.id:
        whats_changed = set(instance.whats_changed())

        # If we are modifying any of important fields, issue a recheck or reprocess
        if 'status' not in whats_changed:
            if instance.status != Socket.STATUSES.PROCESSING and (
                    'install_url' in whats_changed or
                    ('zip_file' in whats_changed and instance.zip_file)
            ):
                instance.set_status(Socket.STATUSES.PROCESSING)

            elif instance.status != Socket.STATUSES.CHECKING and whats_changed.intersection(Socket.RECHECK_FIELDS):
                instance.set_status(Socket.STATUSES.CHECKING)


@receiver(post_save, sender=Socket, dispatch_uid='socket_post_save_handler')
def socket_post_save_handler(sender, instance, created, using, **kwargs):
    if instance.is_live:
        if instance.has_changed('zip_file') and instance.old_value('zip_file'):
            instance.old_value('zip_file').delete(save=False)

        if instance.status == Socket.STATUSES.CHECKING:
            add_post_transaction_success_operation(SocketCheckerTask.delay,
                                                   using=using,
                                                   instance_pk=get_current_instance().pk)

        elif instance.status == Socket.STATUSES.PROCESSING:
            add_post_transaction_success_operation(SocketProcessorTask.delay,
                                                   using=using,
                                                   instance_pk=get_current_instance().pk)


@receiver(post_delete, sender=Socket, dispatch_uid='socket_post_delete_handler')
def socket_post_delete_handler(sender, instance, using, **kwargs):
    # Clean up class that are no longer referenced.
    for class_name, field_dict in instance.installed.get(ClassDependency.yaml_type, {}).items():
        unref_data_klass(instance.pk, class_name, field_dict, using=using)

    # Delete zip file and s3 files.
    if instance.zip_file:
        instance.zip_file.delete(save=False)
    DeleteFilesTask.delay(instance.get_storage_path())


@receiver(pre_save, sender=SocketEnvironment, dispatch_uid='socket_environment_pre_save_handler')
def socket_environment_pre_save_handler(sender, instance, using, **kwargs):
    if instance.is_live and instance.id:
        whats_changed = set(instance.whats_changed())

        # If we are modifying any of important fields, issue a reprocess
        if 'status' not in whats_changed and instance.status != SocketEnvironment.STATUSES.PROCESSING \
                and 'zip_file' in whats_changed and instance.zip_file:
            instance.set_status(SocketEnvironment.STATUSES.PROCESSING)


@receiver(post_save, sender=SocketEnvironment, dispatch_uid='socket_environment_post_save_handler')
def socket_environment_post_save_handler(sender, instance, created, using, **kwargs):
    if instance.is_live:
        if instance.has_changed('zip_file') and instance.old_value('zip_file'):
            instance.old_value('zip_file').delete(save=False)

        if instance.status == SocketEnvironment.STATUSES.PROCESSING:
            add_post_transaction_success_operation(SocketEnvironmentProcessorTask.delay,
                                                   using=using,
                                                   instance_pk=get_current_instance().pk,
                                                   environment_pk=instance.pk)


@receiver(post_delete, sender=SocketEnvironment, dispatch_uid='socket_environment_post_delete_handler')
def socket_environment_post_delete_handler(sender, instance, **kwargs):
    # Delete associated file.
    if instance.fs_file:
        instance.fs_file.delete(save=False)
    if instance.zip_file:
        instance.zip_file.delete(save=False)
