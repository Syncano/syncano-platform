# coding=UTF8
import logging
import os
import tempfile

from django.conf import settings
from django.core.files import File
from django.core.files.storage import default_storage
from django.db import models
from django.utils import timezone
from jsonfield import JSONField

from apps.core.abstract_models import (
    CreatedUpdatedAtAbstractModel,
    LabelDescriptionAbstractModel,
    LiveAbstractModel,
    MetadataAbstractModel
)
from apps.core.exceptions import SyncanoException
from apps.core.helpers import MetaIntEnum, generate_key
from apps.core.permissions import FULL_PERMISSIONS
from apps.instances.models import Instance, InstanceIndicator

from .exceptions import EmptyBackupException
from .site import default_site
from .storage import SolutionZipStorage, ZipStorage
from apps.core.backends.storage import DefaultStorage

Admin = settings.AUTH_USER_MODEL

logger = logging.getLogger(__name__)


def backup_filename(backup, filename):
    return os.path.join(backup.storage_path, "backup.zip")


class Backup(LiveAbstractModel, CreatedUpdatedAtAbstractModel, LabelDescriptionAbstractModel, MetadataAbstractModel):
    PERMISSION_CONFIG = {
        'admin': {
            'full': FULL_PERMISSIONS,
        }
    }

    class STATUSES(MetaIntEnum):
        ABORTED = -2, 'aborted'
        ERROR = -1, 'error'
        SCHEDULED = 0, 'scheduled'
        RUNNING = 1, 'running'
        UPLOADING = 2, 'uploading'
        SUCCESS = 3, 'success'

    owner = models.ForeignKey(Admin, related_name='backups', on_delete=models.CASCADE)
    status = models.SmallIntegerField(choices=STATUSES.as_choices(), default=STATUSES.SCHEDULED.value)
    status_info = models.TextField(blank=True)
    instance = models.ForeignKey(Instance, null=True, on_delete=models.SET_NULL, related_name='backups')
    archive = models.FileField(upload_to=backup_filename)
    size = models.BigIntegerField(null=True)
    query_args = JSONField(default={})
    details = JSONField(default={})
    location = models.TextField(default=settings.LOCATION, db_index=True)

    class Meta:
        ordering = ('id',)

    def __str__(self):
        return 'Backup[id=%s, status=%s, owner_id=%s]' % (self.id, self.get_status_display(), self.owner_id)

    def change_status(self, status, status_info=''):
        now = timezone.now()
        Backup.objects.filter(pk=self.pk).update(status=status, status_info=status_info, updated_at=now)

    @property
    def is_partial(self):
        return bool(self.query_args)

    @property
    def storage_path(self):
        if not self.pk or not self.owner_id:
            raise AttributeError('You have to first save Backup instance to access this attribute.')
        return "backups/{}/{}".format(self.owner_id, self.pk)

    def run(self):
        if self.status != self.STATUSES.SCHEDULED:
            return

        if self.instance is None:
            raise EmptyBackupException()

        self.change_status(self.STATUSES.RUNNING)

        with tempfile.SpooledTemporaryFile() as tmp:
            if self.is_partial:
                storage = SolutionZipStorage.open(tmp, 'w')
            else:
                storage = ZipStorage.open(tmp, 'w', storage_path=os.path.join(self.storage_path, 'files'),
                                          location=settings.LOCATION)

            try:
                default_site.backup_instance(storage, self.instance, self.query_args)
                storage.close()
                tmp.seek(0)
                self.details = storage.details
                self.archive = File(tmp, name="backup.zip")
                if self.is_partial:
                    self.size = self.archive.size
                else:
                    self.size = self.archive.size + storage.storage_size

                self.save()
                self.change_status(self.STATUSES.SUCCESS)
            except SyncanoException as e:
                storage.close()
                self.change_status(self.STATUSES.ERROR, e.detail)


def restore_filename(restore, filename):
    return 'restores/{}/{}.zip'.format(restore.owner_id, generate_key())


class Restore(CreatedUpdatedAtAbstractModel, LabelDescriptionAbstractModel):
    PERMISSION_CONFIG = {
        'admin': {
            'full': FULL_PERMISSIONS,
        }
    }

    class STATUSES(MetaIntEnum):
        ABORTED = -2, 'aborted'
        ERROR = -1, 'error'
        SCHEDULED = 0, 'scheduled'
        RUNNING = 1, 'running'
        SUCCESS = 3, 'success'

    owner = models.ForeignKey(Admin, related_name='+', on_delete=models.CASCADE)
    status = models.SmallIntegerField(choices=STATUSES.as_choices(), default=STATUSES.SCHEDULED.value)
    status_info = models.TextField(blank=True)
    target_instance = models.ForeignKey(Instance, null=False, on_delete=models.CASCADE)
    backup = models.ForeignKey(Backup, null=True, on_delete=models.CASCADE)
    archive = models.FileField(upload_to=restore_filename, null=True)

    class Meta:
        ordering = ('id',)

    def __str__(self):
        return 'Restore[id=%s, label=%s, owner_id=%s]' % (self.id, self.label, self.owner_id)

    def change_status(self, status, status_info=''):
        now = timezone.now()
        Restore.objects.filter(pk=self.pk).update(status=status, status_info=status_info, updated_at=now)

    def run(self):
        self.change_status(self.STATUSES.RUNNING)

        if self.backup_id:
            self.backup.archive.storage = DefaultStorage.create_storage(self.backup.location)
            fileobject = self.backup.archive.file
            is_partial = self.backup.is_partial
        elif self.archive:
            fileobject = self.archive.file
            is_partial = True
        else:
            raise Exception('You have to provide either backup or archive file.')

        if is_partial:
            storage = SolutionZipStorage.open(fileobject, 'r')
        else:
            storage = ZipStorage.open(fileobject, 'r', storage_path=self.backup.storage_path, location=self.backup.location)
        default_site.restore_to_new_schema(storage, self.target_instance, partial=is_partial)
        storage.close()

        InstanceIndicator.refresh(self.target_instance, storage.storage_size)
        self.change_status(self.STATUSES.SUCCESS)
