from apps.backups import site
from apps.backups.options import ModelBackupByName

from .models import ResponseTemplate

site.register(ResponseTemplate, ModelBackupByName)
