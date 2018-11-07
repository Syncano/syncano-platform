# coding=UTF8
import cProfile
import io
import os
from datetime import datetime

from django.conf import settings
from django.http import HttpResponse
from django.utils.encoding import force_bytes
from py_zipkin.zipkin import zipkin_span

from apps.core import zipkin
from apps.core.helpers import get_request_cache, get_schema_cache, set_tracing_attrs
from apps.data.models import DataObject
from apps.instances.helpers import set_current_instance


def clear_request_data():
    get_request_cache().clear()
    get_schema_cache().clear()
    set_tracing_attrs(None)
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


class ZipkinMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        self.zipkin_attrs = zipkin.create_zipkin_attr_from_request(request)
        set_tracing_attrs(self.zipkin_attrs)

        if self.zipkin_attrs.is_sampled:
            self.zipkin_context = zipkin_span(
                service_name=settings.TRACING_SERVICE_NAME,
                span_name='{0} {1}'.format(request.method, force_bytes(request.path)),
                zipkin_attrs=self.zipkin_attrs,
                transport_handler=zipkin.transport_handler,
                host='127.0.0.1',
                port=443,
            )
            self.zipkin_context.start()

        response = self.get_response(request)

        if self.zipkin_attrs.is_sampled:
            self.zipkin_context.update_binary_annotations(
                zipkin.get_binary_annotations(request, response),
            )
            self.zipkin_context.stop()
        return response
