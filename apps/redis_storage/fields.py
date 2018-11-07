# coding=UTF8
from datetime import datetime

import rapidjson as json
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.encoding import force_text
from rest_framework.settings import api_settings

EPOCH_SHIFT = 1314220021721


class RedisField:
    def __init__(self, default=None):
        self.default = default

    def get_default_value(self):
        if callable(self.default):
            return self.default()
        return self.default

    def load(self, value):
        raise NotImplementedError  # pragma: no cover

    def dump(self, value):
        raise NotImplementedError  # pragma: no cover


class CharField(RedisField):
    def load(self, value):
        return value

    def dump(self, value):
        return value


class IntegerField(RedisField):
    def load(self, value):
        return int(value)

    def dump(self, value):
        return str(value)


class AutoField(IntegerField):
    def __init__(self):
        super().__init__()

    def get_next_value(self, obj, **kwargs):
        # Format object key with pk=seq to get sequence key
        sequence_key = obj.get_object_key(pk='seq', **kwargs)
        value = obj.redis_cli.incr(sequence_key)
        ttl = obj.get_ttl(**kwargs)
        if ttl:
            obj.redis_cli.expire(sequence_key, ttl * 2)
        return value


class DatetimeField(RedisField):
    def __init__(self, default=None, auto_now_add=False):
        self.auto_now_add = auto_now_add
        super().__init__(default=default)

    def initial_value(self):
        if self.auto_now_add:
            return timezone.now()
        return None

    def load(self, value):
        return parse_datetime(force_text(value))

    def dump(self, value):
        if not isinstance(value, datetime):
            value = self.load(value)
        return value.strftime(api_settings.DATETIME_FORMAT)


class JSONField(RedisField):
    def load(self, value):
        try:
            return json.loads(value)
        except ValueError:
            return None

    def dump(self, value):
        try:
            return json.dumps(value)
        except UnicodeEncodeError:
            return None


class BooleanField(RedisField):
    def load(self, value):
        return value == 't'

    def dump(self, value):
        return 't' if value else 'f'
