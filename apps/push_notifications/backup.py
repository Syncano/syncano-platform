from apps.backups import site

from .models import APNSConfig, APNSDevice, GCMConfig, GCMDevice

site.register([GCMDevice, GCMConfig, APNSDevice, APNSConfig])
