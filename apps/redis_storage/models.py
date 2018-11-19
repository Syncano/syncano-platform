# coding=UTF8
from django.core.exceptions import ObjectDoesNotExist
from django.utils.encoding import force_bytes
from redis import WatchError
from retrying import retry

from apps.core.helpers import redis
from apps.instances.helpers import get_current_instance
from apps.redis_storage.fields import AutoField, RedisField


class RedisModelBase(type):
    def __new__(mcs, name, bases, attrs):
        super_new = super().__new__

        new_fields = {}
        new_attrs = {'fields': new_fields}

        for base in bases:
            new_fields.update(base.fields)

        for attr, value in attrs.items():
            if isinstance(value, RedisField):
                new_fields[attr] = value
            else:
                new_attrs[attr] = value

        new_type = super_new(mcs, name, bases, new_attrs)

        # Augment template field based on args if needed
        for template_field in ('list_template', 'object_template'):
            template_value = getattr(new_type, '_{}'.format(template_field)).format(class_name=name)
            template_args = getattr(new_type, '{}_args' .format(template_field), None)
            if template_args:
                template_value += ':{}'.format(template_args)

            # For tenant model prepend instance id
            if new_type.tenant_model:
                template_value = '{{instance.id}}:rdb:{}'.format(template_value)
            setattr(new_type, template_field, template_value)

        return new_type


class RedisModel(metaclass=RedisModelBase):
    _list_template = '{class_name}:set'
    _object_template = '{class_name}:{{pk}}'

    redis_cli = redis

    # Define to augment relevant templates (add suffix) for list, object and sequence keys
    list_template_args = None
    object_template_args = None
    seq_template_args = None

    # Override default ordering of objects on list
    default_ordering = 'desc'
    # Max object list size
    list_max_size = None
    # Time to live for objects, None means infinite
    ttl = None
    # Time to live for objects that were trimmed (removed from list due to list_max_size)
    trimmed_ttl = None
    # If tenant_model is True, all objects are bound to current Instance at time of creation
    tenant_model = False

    id = AutoField()
    pk_field = 'id'

    def __init__(self, _saved=False, **kwargs):
        self._saved = _saved

        for field, field_obj in self.fields.items():
            if field in kwargs:
                setattr(self, field, kwargs[field])
            else:
                setattr(self, field, field_obj.get_default_value())

    @property
    def pk(self):
        return getattr(self, self.pk_field)

    def _save_object(self, pipe, object_key, update_fields, ttl=None):
        for field in update_fields:
            value = getattr(self, field, None)
            field_obj = self.fields[field]
            if value is None and hasattr(field_obj, 'initial_value'):
                value = field_obj.initial_value()
                setattr(self, field, value)

            if value is not None:
                value = field_obj.dump(value)
            if value is not None:
                pipe.hset(object_key, field, value)
            elif self._saved:
                pipe.hdel(object_key, field)

        if ttl:
            pipe.expire(object_key, ttl)

    def _save(self, object_key, update_fields, **kwargs):
        trimming = False
        ttl = self.get_ttl(**kwargs)

        with self.redis_cli.pipeline() as pipe:
            self._save_object(pipe, object_key, update_fields, ttl)

            if not self._saved:
                # Save to list if not added already
                list_key = self.get_list_key(**kwargs)
                pipe.zadd(list_key, self.pk, object_key)
                if ttl:
                    pipe.expire(list_key, ttl)
                list_max_size = self.get_list_max_size(**kwargs)
                if list_max_size and self.pk > list_max_size:
                    trimming = True
                    trim = -(list_max_size + 1)
                    pipe.zrange(list_key, 0, trim)
                    pipe.zremrangebyrank(list_key, 0, trim)

            data = pipe.execute()

            trimmed_ttl = self.get_trimmed_ttl(**kwargs)
            if trimming and trimmed_ttl and data[-2]:
                for key in data[-2]:
                    pipe.expire(key, trimmed_ttl)
                pipe.execute()

    def save(self, update_fields=None, **kwargs):
        if not self._saved:
            if update_fields:
                raise RuntimeError('update_fields cannot be specified for unsaved object.')
            if self.id is None:
                self.id = self.fields['id'].get_next_value(self, **kwargs)

        update_fields = update_fields or self.fields.keys()
        object_key = self.get_object_key(pk=self.pk, **kwargs)

        self._save(object_key, update_fields, **kwargs)
        self._saved = True

    def delete(self, **kwargs):
        object_key = self.get_object_key(pk=self.pk, **kwargs)
        list_key = self.get_list_key(**kwargs)

        with self.redis_cli.pipeline(transaction=False) as pipe:
            pipe.delete(object_key)
            pipe.zrem(list_key, object_key)
            pipe.execute()

    @classmethod
    def _format_key(cls, key, **kwargs):
        if cls.tenant_model and 'instance' not in kwargs:
            kwargs['instance'] = get_current_instance()
        return key.format(**kwargs)

    @classmethod
    def get_list_key(cls, **kwargs):
        return cls._format_key(cls.list_template, **kwargs)

    @classmethod
    def get_object_key(cls, **kwargs):
        return cls._format_key(cls.object_template, **kwargs)

    @classmethod
    def get_list_max_size(cls, **kwargs):
        return cls.list_max_size

    @classmethod
    def get_ttl(cls, **kwargs):
        return cls.ttl

    @classmethod
    def get_trimmed_ttl(cls, **kwargs):
        return cls.trimmed_ttl

    @classmethod
    def load(cls, **kwargs):
        for field, value in kwargs.items():
            if value is not None:
                kwargs[field] = cls.fields[field].load(value)
        return cls(_saved=True, **kwargs)

    @classmethod
    @retry(retry_on_exception=lambda x: isinstance(x, WatchError), stop_max_attempt_number=3)
    def _update(cls, pipe, object_key, updated, expected=None):
        if expected:
            pipe.watch(object_key)
            for field, value in expected.items():
                # Do not save if field is not of the expected value
                if pipe.hget(object_key, field) != force_bytes(expected[field]):
                    return False
            pipe.multi()

        # Start the actual save
        for field, value in updated.items():
            if value is not None:
                value = cls.fields[field].dump(value)

            if value is not None:
                pipe.hset(object_key, field, value)
            else:
                pipe.hdel(object_key, field)

        if cls.ttl:
            pipe.expire(object_key, cls.ttl)
        pipe.execute()
        return True

    @classmethod
    def update(cls, pk, updated, expected=None, **kwargs):
        object_key = cls.get_object_key(pk=pk, **kwargs)

        with cls.redis_cli.pipeline() as pipe:
            return cls._update(pipe, object_key, updated, expected)

    @classmethod
    def get(cls, pk, **kwargs):
        key = cls.get_object_key(pk=pk, **kwargs)
        object_data = cls.redis_cli.hgetall(key)

        if object_data:
            return cls.load(**{k.decode(): v.decode() for k, v in object_data.items()})
        raise ObjectDoesNotExist()

    @classmethod
    def list(cls, min_pk=None, max_pk=None, ordering='desc', limit=100, deferred_fields=None, **kwargs):
        list_key = cls.get_list_key(**kwargs)
        deferred_fields = deferred_fields or {}
        fields_list = [field_key for field_key in cls.fields.keys() if field_key not in deferred_fields]
        redis_cli = cls.redis_cli
        if (min_pk is not None and min_pk <= 0) or (max_pk is not None and max_pk <= 0):
            return []

        if ordering == 'desc':
            keys_list = redis_cli.zrevrangebyscore(list_key, max_pk or '+inf', min_pk or '-inf', start=0, num=limit)
        else:
            keys_list = redis_cli.zrangebyscore(list_key, min_pk or '-inf', max_pk or '+inf', start=0, num=limit)

        with redis_cli.pipeline() as pipe:
            for key in keys_list:
                pipe.hmget(key, *fields_list)
            data_list = pipe.execute()

        object_list = []
        for object_data in data_list:
            # If any of object properties are set, add to results
            if any(object_data):
                object_data = [v.decode() if v is not None else None for v in object_data]
                obj = cls.load(**dict(zip(fields_list, object_data)))
                object_list.append(obj)

        return object_list

    @classmethod
    def create(cls, **kwargs):
        obj = cls(**kwargs)
        obj.save(**kwargs)
        return obj
