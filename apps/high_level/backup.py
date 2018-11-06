# coding=UTF8
from apps.backups import site
from apps.backups.options import ModelBackupByName

from .models import DataObjectHighLevelApi

site.register(DataObjectHighLevelApi, ModelBackupByName)
