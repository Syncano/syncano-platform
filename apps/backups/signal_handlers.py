# coding=UTF8
from django.db import transaction
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from apps.core.tasks import DeleteFilesTask

from .models import Backup, Restore
from .tasks import RunBackupTask, RunRestoreTask


@receiver(post_save, sender=Backup, dispatch_uid='backup_post_save_handler')
def backup_post_save_handler(sender, instance, created, **kwargs):
    if created:
        transaction.on_commit(lambda: RunBackupTask.delay(instance.pk))


@receiver(post_delete, sender=Backup, dispatch_uid='backup_post_delete_handler')
def backup_post_delete_handler(sender, instance, **kwargs):
    storage_path = instance.storage_path
    DeleteFilesTask.delay(storage_path)


@receiver(post_save, sender=Restore, dispatch_uid='restore_post_save_handler')
def restore_post_save_handler(sender, instance, created, **kwargs):
    if created:
        transaction.on_commit(lambda: RunRestoreTask.delay(instance.pk))


@receiver(post_delete, sender=Restore, dispatch_uid='restore_post_delete_handler')
def restore_post_delete_handler(sender, instance, **kwargs):
    if instance.archive:
        transaction.on_commit(lambda: instance.archive.delete(save=False))
