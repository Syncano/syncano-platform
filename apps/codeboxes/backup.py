from apps.backups import site

from .models import CodeBox, CodeBoxSchedule

site.register([CodeBox, CodeBoxSchedule])
