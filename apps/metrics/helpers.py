import calendar
import datetime
from math import floor

import pytz


def timestamp_to_datetime(ts):
    """
    Converts UNIX timestamp to UTC datetime
    """
    return datetime.datetime.utcfromtimestamp(int(ts)).replace(tzinfo=pytz.utc)


def datetime_to_timestamp(dt):
    """
    Converts UTC datetime to UNIX timestamp
    """
    return calendar.timegm(dt.timetuple())


def floor_to_base(x, base=5):
    # Supports datetime
    try:
        return int(base * floor(float(x) / base))
    except TypeError:
        return timestamp_to_datetime(floor_to_base(datetime_to_timestamp(x), base.total_seconds()))
