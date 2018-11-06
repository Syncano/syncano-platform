from apps.backups import site
from apps.backups.options import ModelBackupByName

from .models import Webhook

site.register(Webhook, ModelBackupByName)
