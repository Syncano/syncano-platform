# coding=UTF8
import collections
import hmac
import inspect
import os
import re
import socket
import string
import subprocess
import threading
import time
import uuid
from enum import Enum
from hashlib import sha1
from importlib import import_module
from io import BytesIO
from multiprocessing import TimeoutError
from threading import local

import docker
import gevent.local
import gevent.socket
import lazy_object_proxy
import requests
from django.apps import apps
from django.conf import settings
from django.core.cache import cache
from django.core.cache.backends.locmem import LocMemCache
from django.core.exceptions import EmptyResultSet
from django.db import DEFAULT_DB_ALIAS, IntegrityError, models, router, transaction
from django.db.models import AutoField
from django.db.transaction import get_connection
from django.urls import resolve
from django.utils.encoding import force_text, smart_text
from django.utils.functional import Promise
from django_redis import get_redis_connection
from munch import Munch
from opencensus.common import configuration
from opencensus.trace import execution_context, print_exporter, samplers
from opencensus.trace import tracer as tracer_module
from opencensus.trace.propagation import trace_context_http_header_format
from redis import Redis
from redis.lock import Lock
from requests.exceptions import HTTPError, ReadTimeout
from rest_framework.fields import BooleanField
from rest_framework.reverse import reverse

from apps.core.validators import validate_id

try:
    # try to import uwsgi first as that module is not be available outside of uwsgi context (e.g. during tests)
    import uwsgi
except ImportError:
    uwsgi = None

if socket.socket is gevent.socket.socket:
    LOCAL_STORAGE = gevent.local.local()
else:
    LOCAL_STORAGE = local()

DEFAULT_CACHE_KEY_TEMPLATE = '{schema}:cache:py:%d:{lookup_key}:{kwargs_key}' % settings.CACHE_VERSION
MODEL_VERSION_CACHE_KEY_TEMPLATE = '{schema}:cache:m:%d:{lookup_key}:{pk}:version' % settings.CACHE_VERSION
FUNC_VERSION_CACHE_KEY_TEMPLATE = '0:cache:f:%d:{lookup_key}:{version_key}:version' % settings.CACHE_VERSION

ALL_CONTROL_CHARACTERS = dict.fromkeys(range(33))

REVALIDATE_MAX_RETRY = 2

try:
    redis = get_redis_connection()
except NotImplementedError:
    redis = Redis(host=settings.REDIS_HOST, port=settings.REDIS_PORT, db=settings.REDIS_DB)

docker_client = lazy_object_proxy.Proxy(lambda: docker.from_env(version=settings.DOCKER_VERSION))


def sanitize_text(text):
    if text is not None:
        text = smart_text(text, errors='ignore')
        text = text.translate(ALL_CONTROL_CHARACTERS)
    return text


# Cache functions

def get_local_cache():
    if not hasattr(LOCAL_STORAGE, 'local_cache'):
        LOCAL_STORAGE.local_cache = LocMemCache('local_cache@%i' % hash(threading.currentThread()), {})
    return LOCAL_STORAGE.local_cache


def get_request_cache():
    """
    Request cache is meant to be cleared before every request/task.
    """
    if not hasattr(LOCAL_STORAGE, 'request_cache'):
        LOCAL_STORAGE.request_cache = LocMemCache('request_cache@%i' % hash(threading.currentThread()), {})
    return LOCAL_STORAGE.request_cache


def get_schema_cache():
    """
    Schema cache to be cleared before every request/task.
    """
    if not hasattr(LOCAL_STORAGE, 'schema_cache'):
        LOCAL_STORAGE.schema_cache = dict()
    return LOCAL_STORAGE.schema_cache


_tracer_sampler = None
_tracer_exporter = None
_tracer_propagator = None


def get_tracer_propagator():
    global _tracer_propagator

    if _tracer_propagator is None:
        settings_ = getattr(settings, 'OPENCENSUS', {})
        settings_ = settings_.get('TRACE', {})

        _tracer_propagator = settings_.get('PROPAGATOR', None) or \
            trace_context_http_header_format.TraceContextPropagator()
        if isinstance(_tracer_propagator, str):
            _tracer_propagator = configuration.load(_tracer_propagator)

    return _tracer_propagator


def create_tracer(span_context=None):
    global _tracer_sampler, _tracer_exporter

    if _tracer_sampler is None or _tracer_exporter is None:
        settings_ = getattr(settings, 'OPENCENSUS', {})
        settings_ = settings_.get('TRACE', {})

        _tracer_sampler = settings_.get('SAMPLER', None) or \
            samplers.ProbabilitySampler()
        if isinstance(_tracer_sampler, str):
            _tracer_sampler = configuration.load(_tracer_sampler)

        _tracer_exporter = settings_.get('EXPORTER', None) or \
            print_exporter.PrintExporter()
        if isinstance(_tracer_exporter, str):
            _tracer_exporter = configuration.load(_tracer_exporter)

    return tracer_module.Tracer(
        span_context=span_context,
        sampler=_tracer_sampler,
        exporter=_tracer_exporter,
        propagator=get_tracer_propagator())


def get_current_tracer():
    """Get the current request tracer."""
    return execution_context.get_opencensus_tracer()


def get_current_span():
    return execution_context.get_current_span()


def propagate_uwsgi_params(data):
    for k, v in data.items():
        uwsgi.add_var(k, v)


def get_current_span_propagation():
    tracer = get_current_tracer()
    try:
        return tracer.propagator.to_headers(tracer.span_context)
    except Exception:  # pragma: no cover
        return {}


def get_transaction_blocks_list(using=None):
    using = using or DEFAULT_DB_ALIAS
    if not hasattr(LOCAL_STORAGE, 'transaction_block_list'):
        LOCAL_STORAGE.transaction_block_list = collections.defaultdict(list)
    return LOCAL_STORAGE.transaction_block_list[using]


def get_last_transaction_block_list(using=None):
    return get_transaction_blocks_list(using)[-1]


def add_post_transaction_operation(func, *args, **kwargs):
    using = kwargs.pop('using', None)
    get_last_transaction_block_list(using).append((None, func, args, kwargs))


def add_post_transaction_success_operation(func, *args, **kwargs):
    using = kwargs.pop('using', None)
    if settings.POST_TRANSACTION_SUCCESS_EAGER or not get_connection(using).in_atomic_block:
        func(*args, **kwargs)
    else:
        get_last_transaction_block_list(using).append((True, func, args, kwargs))


def add_post_transaction_error_operation(func, *args, **kwargs):
    using = kwargs.pop('using', None)
    if get_connection(using).in_atomic_block:
        get_last_transaction_block_list(using).append((False, func, args, kwargs))


def get_lock_registry():
    if not hasattr(LOCAL_STORAGE, 'lock_registry'):
        LOCAL_STORAGE.lock_registry = collections.defaultdict(int)
    return LOCAL_STORAGE.lock_registry


class Cached:
    def __init__(self, target, timeout=None, args=(), kwargs=None, key=None, version_key=None, compute_func=None):
        self.target = target
        self.args = args
        self.kwargs = kwargs or dict()
        self.version_key = version_key
        self.compute_func = compute_func

        if hasattr(target, '_meta'):
            type_ = 'model'
            if settings.DEBUG or settings.TESTING:
                self._validate_global_cache_operation()
            self.object_pk = getattr(target, 'pk')
        elif isinstance(target, collections.Callable):
            type_ = 'function'
        else:
            raise RuntimeError('Must specify model or function as a parameter.')

        self.type = type_
        self.lookup_key, self.schema = self._get_lookup_key(key=key, type_=type_, target=target)
        self.timeout = self._get_timeout(timeout=timeout)

        cache_hash = self._get_cache_hash()
        cache_key = DEFAULT_CACHE_KEY_TEMPLATE.format(schema=self.schema, lookup_key=self.lookup_key,
                                                      kwargs_key=cache_hash)

        self.cache_key = sanitize_text(cache_key)
        self.version = None

    def _get_cache_hash(self):
        kwargs = self.kwargs
        args = list(self.args)
        for i in range(len(args)):
            v = args[i]
            if isinstance(v, dict):
                args[i] = frozenset(v.items())

        kwargs_list = list(kwargs.items())
        for i in range(len(kwargs_list)):
            k, v = kwargs_list[i]
            if isinstance(v, list):
                kwargs_list[i] = k, tuple(v)
            elif isinstance(v, dict):
                kwargs_list[i] = k, frozenset(v.items())
        kwargs_key = hash((tuple(args), frozenset(kwargs_list)))
        return kwargs_key

    def _get_timeout(self, timeout):
        if timeout is not None:
            return timeout
        return settings.CACHE_TIMEOUT

    def _validate_global_cache_operation(self):
        target = self.target

        if inspect.isclass(target) and issubclass(target, models.Model):
            from .abstract_models import CacheableAbstractModel

            if not issubclass(target, CacheableAbstractModel):
                raise RuntimeError('To cache model {model_name} you need to inherit CacheableAbstractModel.'.format(
                    model_name=target.__name__))

    def _get_cache_storage(self, local=False):
        if local:
            return get_local_cache()
        return cache

    def _get_lookup_key(self, key, type_, target):
        schema = '0'

        if type_ == 'model':
            app_label = target._meta.app_label
            lookup_name = target._meta.db_table
            if apps.get_app_config(app_label).name in settings.TENANT_APPS:
                from apps.instances.helpers import get_current_instance

                instance = get_current_instance()

                if instance is None:
                    raise target.DoesNotExist()

                schema = str(instance.id)

            return lookup_name, schema

        lookup_name = key
        if key is None:
            lookup_name = target.__module__
            if hasattr(target, '__self__') and target.__self__ and hasattr(target.__self__, '__name__'):
                lookup_name += '.%s' % target.__self__.__name__
            lookup_name += '.%s' % target.__name__

        if self.version_key is not None:
            lookup_name += ':%s' % self.version_key

        return lookup_name, schema

    def _get_cached_value(self, cache_storage):
        cached_value = cache_storage.get(self.cache_key)
        if cached_value is None:
            return None, None, False

        return cached_value[0], cached_value[1], True

    def _compute_value(self):
        type_ = self.type
        target = self.target
        args = self.args
        kwargs = self.kwargs

        if type_ == 'function':
            value = target(*args, **kwargs)
        else:
            if self.compute_func is not None:
                value = self.compute_func()
            else:
                value = target.objects.get(*args, **kwargs)

        return value

    def get(self):
        # Check local storage on versioned data
        if self.is_versioned():
            cached_value, version, ok = self._get_cached_value(self._get_cache_storage(local=True))
            if ok and self._check_version(cached_value, version):
                return cached_value

        # Check global storage
        cached_value, version, ok = self._get_cached_value(self._get_cache_storage())
        if ok:
            if self.is_versioned():
                if self._check_version(cached_value, version):
                    self.set_local(cached_value)
                    return cached_value
            else:
                return cached_value

        # Compute value
        cached_value = self._compute_value()
        self.set(cached_value)
        return cached_value

    def set(self, value):
        cache_storage = self._get_cache_storage()

        if isinstance(value, Munch):
            value = value.toDict()

        cache_storage.set(key=self.cache_key, value=(value, self.version), timeout=self.timeout)

        if self.is_versioned():
            self.set_local(value)
        return value

    def set_local(self, value):
        if isinstance(value, Munch):
            value = value.toDict()

        local_cache_storage = self._get_cache_storage(local=True)
        local_cache_storage.set(key=self.cache_key, value=(value, self.version), timeout=settings.LOCAL_CACHE_TIMEOUT)
        return value

    def is_versioned(self):
        return self.type == 'model' or self.version_key is not None

    def invalidate(self, object=None, immediate=None):
        if object is not None and self.type == 'model' or self.version_key is not None:
            # Set new random version value so that old cache is correctly recognized even if race condition happens.
            # This way invalidates all cached fields at once.
            version_key = self.get_version_key(object)
            self._queue_func(immediate, redis.set, name=version_key, value=generate_key(),
                             ex=self.timeout + 300)

            if getattr(object, 'SYNC_INVALIDATION', False) and len(settings.LOCATIONS) > 1:
                from apps.core.tasks import SyncInvalidationTask
                SyncInvalidationTask.delay(version_key)
            return

        self._queue_func(immediate, self._get_cache_storage().delete, key=self.cache_key)

    def get_version_key(self, object):
        if self.type == 'model':
            object_pk = self.kwargs.get('pk')
            if object_pk is None:
                object_pk = object.pk
            return MODEL_VERSION_CACHE_KEY_TEMPLATE.format(schema=self.schema, lookup_key=self.lookup_key,
                                                           pk=object_pk)
        return FUNC_VERSION_CACHE_KEY_TEMPLATE.format(lookup_key=self.lookup_key, version_key=self.version_key)

    def _queue_func(self, immediate, function, **kwargs):
        immediate = immediate if immediate is not None else not self.is_versioned()
        if immediate:
            function(**kwargs)
        else:
            add_post_transaction_success_operation(function, **kwargs)

    def _check_version(self, obj, version):
        current_version = redis.get(self.get_version_key(obj))
        if current_version:
            # Save current version as a new one, so it is used for `set`
            self.version = current_version
            if force_text(current_version) != force_text(version):
                # If version is a mismatch, return empty result
                return False
        return True


class Command:
    """
    Enables to run subprocess commands in a different thread
    with TIMEOUT option!

    Based on jcollado's solution:
    http://stackoverflow.com/questions/1191374/subprocess-with-timeout/4825933#4825933
    """

    def __init__(self, cmd):
        self.cmd = cmd
        self.process = None

    def run(self, timeout=None, **kwargs):
        def target(**kwargs):
            self.process = subprocess.Popen(self.cmd, **kwargs)
            self.process.communicate()

        thread = threading.Thread(target=target, kwargs=kwargs)
        thread.start()

        thread.join(timeout)
        if thread.is_alive():
            self.process.terminate()
            thread.join()
            raise TimeoutError()

        return self.process.returncode


def get_from_dict(dic, *names, **opts):
    if not names:
        return

    if not isinstance(dic, dict):
        dic = {}

    default = opts.get('default')
    getlist = opts.get('getlist', False)
    method = dic.getlist if getlist and hasattr(dic, 'getlist') else dic.get

    if len(names) == 1:
        value = method(names[0], default)
        return [value] if not hasattr(dic, 'getlist') and getlist else value

    return [method(name, default) for name in names]


def get_from_request_query_params(request, *names, **opts):
    return get_from_dict(request.query_params, *names, **opts)


def get_from_request_data(request, *names, **opts):
    return get_from_dict(request.data, *names, **opts)


def generate_key(parity=None):
    new_uuid = uuid.uuid4()
    digest = hmac.new(new_uuid.bytes, digestmod=sha1).hexdigest()
    if parity is not None:
        last = int(digest[-1], 16)
        if parity:
            last &= 0b1110
        else:
            last |= 0b1
        digest = digest[:-1] + '{0:x}'.format(last)

    return digest


def check_parity(key):
    return not bool(int(key[-1], 16) & 0b1)


def import_class(cls):
    module, cls = cls.rsplit('.', 1)
    cls = getattr(import_module(module), cls)
    return cls


def iterate_over_queryset_in_chunks(queryset, value='pk', chunk_size=100):
    """Iterate over queryset of flat values in efficient way."""
    last_pk = 0

    if value != 'pk':
        values_list = ('pk', value)
    else:
        values_list = ('pk',)
    queryset = queryset.values_list(*values_list)

    while True:
        object_list = list(queryset.filter(pk__gt=last_pk)[:chunk_size])
        if not object_list:
            break
        yield [obj[-1] for obj in object_list]
        last_pk = object_list[-1][0]


def validate_field(field, value, validate_none=True):
    value = field.to_python(value)

    if not validate_none and value is None:
        return value

    for validator in field.validators:
        validator(value)
    if isinstance(field, AutoField):
        validate_id(value)
    return value


def is_query_param_true(request, name):
    param = request.query_params.get(name)
    return param and param in BooleanField.TRUE_VALUES


def cast_if_promise(value):
    return str(value) if isinstance(value, Promise) else evaluate_promises(value)


def evaluate_promises(data):
    if isinstance(data, dict):
        return {key: cast_if_promise(value) for key, value in data.items()}
    if isinstance(data, (tuple, list)):
        return [cast_if_promise(value) for value in data]
    return str(data) if isinstance(data, Promise) else data


def get_count_estimate_from_queryset(queryset, real_limit=1000):
    return get_count_estimate_from_query(queryset.query, real_limit=real_limit, using=queryset.db)


def get_count_estimate_from_query(query, real_limit=1000, using=None):
    compiler = query.get_compiler(using)
    try:
        sql, params = compiler.as_sql()
    except EmptyResultSet:
        return 0
    cursor = compiler.connection.cursor()
    sql = cursor.mogrify(sql, params)
    sql = force_text(sql).replace("'", "''")
    cursor.execute("SELECT count_estimate('%s', %d)" % (sql, real_limit))
    return cursor.fetchone()[0]


def camel_to_under(name):
    # credits for paste
    # http://stackoverflow.com/questions/1175208/elegant-python-function-to-convert-camelcase-to-snake-case
    sub = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
    return re.sub('([a-z0-9])([A-Z])', r'\1_\2', sub).lower()


def dict_get_any(dct, *args):
    for arg in args:
        if arg in dct:
            return dct[arg]


def run_api_view(viewname, args, request, **kwargs):
    if getattr(request, 'instance', None):
        kwargs['instance'] = request.instance

    view, v_args, v_kwargs = resolve(
        reverse(viewname, args=args, request=request)
    )
    v_kwargs.update(kwargs)
    return view(request._request, *v_args, **v_kwargs)


def download_file(url, timeout, max_size, out=None):
    start = time.time()
    size = 0

    r = requests.get(url, stream=True, timeout=timeout)
    r.raise_for_status()

    if int(r.headers.get('Content-Length', 0)) > max_size:
        raise HTTPError('Response too large.')

    out_file = out or BytesIO()

    for chunk in r.iter_content(1024):
        if time.time() - start > timeout:
            raise ReadTimeout('Timeout reached.')

        size += len(chunk)
        if size > max_size:
            raise HTTPError('Response too large.')
        out_file.write(chunk)

    if out is None:
        return out_file.getvalue()
    return out_file


def format_error(errors):
    if isinstance(errors, list):
        return errors[0]
    if isinstance(errors, str):
        return errors

    key = list(errors.keys())[0]
    return '"{}": {}'.format(key, format_error(errors[key]))


BASE_LIST = string.digits + string.ascii_letters
BASE_DICT = {c: i for i, c in enumerate(BASE_LIST)}


def base_decode(string, reverse_base=BASE_DICT):
    length = len(reverse_base)
    return sum((length ** i) * reverse_base[c] for i, c in enumerate(string[::-1]))


def base_encode(integer, base=BASE_LIST):
    if integer == 0:
        return base[0]

    length = len(base)
    ret = ''
    while integer != 0:
        ret = base[integer % length] + ret
        integer = int(integer / length)

    return ret


def make_token(instance, expiration_time=600):
    instance_pk = base_encode(instance.pk)
    epoch = base_encode(int(time.time()) + expiration_time)
    hash = hmac.new('{}:{}:{}'.format(instance_pk, epoch, settings.SECRET_KEY).encode(),
                    digestmod=sha1).hexdigest()
    return '{}:{}:{}'.format(instance_pk, epoch, hash)


def verify_token(token):
    token = token.split(':', 2)
    if len(token) != 3:
        return
    instance_pk, epoch, hash = token

    # Check hash
    verify_hash = hmac.new('{}:{}:{}'.format(instance_pk, epoch, settings.SECRET_KEY).encode(),
                           digestmod=sha1).hexdigest()
    if verify_hash != hash:
        return

    # Check if key has not expired
    epoch = base_decode(epoch)
    if epoch < int(time.time()):
        return

    return base_decode(instance_pk)


class MetaEnumBase(Enum):
    @classmethod
    def as_choices(cls):
        return sorted([(member.value, member.verbose) for member in cls])

    @classmethod
    def _missing_(cls, value):
        for member in cls:
            if member.value == value or member.verbose == value:
                return member
        super()._missing_(value)

    def __eq__(self, other):
        if isinstance(other, type(self.value)):
            return self.value == other
        return super().__eq__(other)

    def __hash__(self):
        return hash((self.value))

    def __str__(self):
        return str(self.value)


class MetaEnum(MetaEnumBase):
    def __init__(self, *args):
        self.verbose = self._value_ = args[0]
        if len(args) == 2:
            self.verbose = args[1]


class MetaIntEnum(int, MetaEnumBase):
    def __new__(cls, *args, **kwargs):
        obj = int.__new__(cls, args[0])
        obj.verbose = obj._value_ = args[0]
        if len(args) > 1:
            obj.verbose = args[1]
        return obj


def glob(pattern, subj):
    # Empty pattern can only match empty subject
    if pattern == '':
        return subj == pattern

    # If the pattern _is_ a glob, it matches everything
    if pattern == '*':
        return True

    parts = pattern.split('*')
    if len(parts) == 1:
        # No globs in pattern, so test for equality
        return subj == pattern

    leading_glob = pattern.startswith('*')
    trailing_glob = pattern.endswith('*')

    # Check the first section. Requires special handling.
    if not leading_glob and not subj.startswith(parts[0]):
        return False

    # Go over the middle parts and ensure they match.
    for i in range(len(parts) - 2):
        part = parts[i]
        if part not in subj:
            return False
        # Trim evaluated text from subj as we loop over the pattern.
        subj = subj[subj.index(part) + len(part):]

    return trailing_glob or subj.endswith(parts[-1])


class ReentrantLock(Lock):
    """
    A reentrant lock implementation.
    """

    def acquire(self, blocking=None, blocking_timeout=None):
        registry = get_lock_registry()
        if registry[self.name] > 0 or super().acquire(blocking, blocking_timeout):
            registry[self.name] += 1
            return True
        return False

    def release(self):
        registry = get_lock_registry()
        if registry[self.name] > 1:
            registry[self.name] -= 1
            return

        super().release()
        registry[self.name] -= 1
        if registry[self.name] <= 0:
            del registry[self.name]


def get_cur_loc_env(name, default=None):
    return get_loc_env(settings.LOCATION, name, default)


def get_loc_env(location, name, default=None):
    return os.environ.get('{}_{}'.format(location.upper(), name), os.environ.get(name, default))


def revalidate_integrityerror(model, save_func, validate_func):
    db = router.db_for_write(model)
    err = None

    for i in range(REVALIDATE_MAX_RETRY):
        try:
            with transaction.atomic(db):
                return save_func()
        except IntegrityError as e:
            if err is None:
                err = e

            validate_func()

    raise err
