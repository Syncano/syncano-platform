from apps.backups import site
from apps.backups.options import ModelBackupByName

from .models import Channel

site.register(Channel, ModelBackupByName)
