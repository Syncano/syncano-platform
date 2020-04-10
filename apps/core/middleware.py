# coding=UTF8
import cProfile
import io
import logging
import os
from datetime import datetime

import django
from django.conf import settings
from django.db import connection
from django.http import HttpResponse
from opencensus.ext.django.middleware import BLACKLIST_HOSTNAMES, BLACKLIST_PATHS
from opencensus.ext.django.middleware import OpencensusMiddleware as _OpencensusMiddleware
from opencensus.ext.django.middleware import _get_current_tracer, _trace_db_call, utils
from raven.contrib.django.resolver import RouteResolver

from apps.core.helpers import (
    get_request_cache,
    get_schema_cache,
    get_tracer_exporter,
    get_tracer_propagator,
    get_tracer_sampler
)
from apps.data.models import DataObject
from apps.instances.helpers import set_current_instance

logger = logging.getLogger(__name__)


def clear_request_data():
    get_request_cache().clear()
    get_schema_cache().clear()
    set_current_instance(None)
    DataObject.loaded_klass = None


class PrepareRequestMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        clear_request_data()
        return self.get_response(request)


class InstrumentMiddleware:  # pragma: no cover
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if 'profile' in request.GET:
            request.profiler = cProfile.Profile()
            request.profiler.enable()

        response = self.get_response(request)

        if hasattr(request, 'profiler'):
            import pstats

            request.profiler.disable()
            stamp = (request.META['REMOTE_ADDR'], datetime.now())
            request.profiler.dump_stats('/tmp/%s-%s.pro' % stamp)

            stream = io.StringIO()
            stats = pstats.Stats('/tmp/%s-%s.pro' % stamp, stream=stream)
            stats.strip_dirs()
            stats.sort_stats('time')
            stats.print_stats(12)
            stats.print_callers(12)
            stats.print_callees(12)
            os.remove('/tmp/%s-%s.pro' % stamp)
            data = b'<pre>' + stream.getvalue().encode() + b'</pre>'
            data += b'<br/ >Original response:<pre>' + response.content + b'</pre>'
            stream.close()
            return HttpResponse(content=data)
        return response


class OpencensusMiddleware(_OpencensusMiddleware):
    def __init__(self, get_response=None):
        self.get_response = get_response

        self.propagator = get_tracer_propagator()
        self.exporter = get_tracer_exporter()
        self.sampler = get_tracer_sampler()

        settings_ = getattr(settings, 'OPENCENSUS', {})
        settings_ = settings_.get('TRACE', {})
        self.blacklist_paths = settings_.get(BLACKLIST_PATHS, None)
        self.blacklist_hostnames = settings_.get(BLACKLIST_HOSTNAMES, None)

        self.resolver = RouteResolver()

    def process_view(self, request, view_func, *args, **kwargs):
        """Process view is executed before the view function, here we get the
        function name add set it as the span name.
        """

        # Do not trace if the url is blacklisted
        if utils.disable_tracing_url(request.path, self.blacklist_paths):
            return

        try:
            # Get the current span and set the span name to the current
            # function name of the request.
            tracer = _get_current_tracer()
            span = tracer.current_span()
            span.name = self.resolver.resolve(request.path_info)
            tracer.add_attribute_to_current_span(
                attribute_key='django.view',
                attribute_value=utils.get_func_name(view_func))
        except Exception:  # pragma: no cover
            logger.error('Failed to trace request', exc_info=True)

    def __call__(self, request):
        # Fix: from https://github.com/census-instrumentation/opencensus-python/pull/811
        if django.VERSION >= (2,):  # pragma: NO COVER
            with connection.execute_wrapper(_trace_db_call):
                return super(OpencensusMiddleware, self).__call__(request)
        return super(OpencensusMiddleware, self).__call__(request)
