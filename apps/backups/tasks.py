# coding=UTF8
from zipfile import BadZipfile

from celery.utils.log import get_task_logger
from settings.celeryconf import app, register_task

from apps.core.exceptions import SyncanoException
from apps.core.tasks import DeleteFilesTask

from .models import Backup, Restore

logger = get_task_logger(__name__)


@register_task
class RunBackupTask(app.Task):
    def run(self, backup_pk):
        try:
            backup = Backup.objects.get(pk=backup_pk)
        except Backup.DoesNotExist:
            logger.warning('Cannot process Backup[pk=%s] as it no longer exists.',
                           backup_pk)
            return

        try:
            backup.run()
        except SyncanoException as e:
            backup.change_status(Backup.STATUSES.ERROR, e)
            logger.warning('Error processing Backup[pk=%s]: %s', backup_pk, e)
        except Exception:
            logger.exception('Error processing Backup[pk=%s].', backup_pk)
            DeleteFilesTask.delay(backup.storage_path)
            backup.change_status(status=Backup.STATUSES.ERROR)
            raise


@register_task
class RunRestoreTask(app.Task):
    def run(self, restore_pk):
        try:
            restore = Restore.objects.get(pk=restore_pk)
        except Restore.DoesNotExist:
            logger.warning('Cannot process Restore[pk=%s] as it no longer exists.',
                           restore_pk)
            return

        # Check if there is already a restore scheduled
        if Restore.objects.filter(pk__lt=restore_pk,
                                  target_instance=restore.target_instance,
                                  status__in=(Restore.STATUSES.SCHEDULED, Restore.STATUSES.RUNNING)).exists():
            restore.change_status(Restore.STATUSES.ABORTED, 'Restore already scheduled on specified instance.')

        try:
            restore.run()
        except SyncanoException as e:
            restore.change_status(Restore.STATUSES.ERROR, e)
            logger.warning('Error processing Restore[pk=%s]: %s', restore_pk, e)
        except BadZipfile:
            restore.change_status(Restore.STATUSES.ERROR, 'Invalid file.')
            logger.warning('Error processing Restore[pk=%s]: Bad zipfile.', restore_pk)
        except Exception:
            logger.exception('Error processing Restore[pk=%s].', restore_pk)
            restore.change_status(Restore.STATUSES.ERROR, 'Internal error occurred.')
            raise
