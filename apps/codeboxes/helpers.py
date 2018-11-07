# coding=UTF8
import rapidjson as json
from celery.schedules import crontab
from django.utils import timezone

from apps.core.helpers import redis


class crontab_with_timezone(crontab):
    @crontab.tz.setter
    def set_tz(self, tz):
        return tz


def compute_remaining_seconds_from_crontab(crontab_string, tz, now=None):
    """
    Compute seconds from `now` to the next supposed execution.
    :param crontab_string: string used to specify schedule, e.g `*/2 * * * *` - every two minutes
    :return: amount of seconds from now to then
    """

    crontab_parts = crontab_string.split()
    now = now or timezone.now()
    parsed_crontab = create_crontab(*crontab_parts, nowfun=lambda: now)
    parsed_crontab.tz = tz
    return parsed_crontab.is_due(now)[1]


def create_crontab(minute, hour, day_of_month, month_of_year, day_of_week, nowfun=None):
    return crontab_with_timezone(minute=minute, hour=hour,
                                 day_of_month=day_of_month, month_of_year=month_of_year,
                                 day_of_week=day_of_week,
                                 nowfun=nowfun)


def get_codebox_spec(spec_key):
    serialized_spec = redis.get(spec_key)
    if serialized_spec is not None:
        try:
            return json.loads(serialized_spec)
        except ValueError:
            return None
