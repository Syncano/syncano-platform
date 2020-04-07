# coding=UTF8
import gevent.monkey  # isort:skip

gevent.monkey.patch_all()  # noqa

import logging
import os

import django
from django.conf import settings
from django.core.handlers.wsgi import WSGIRequest
from django.http.response import HttpResponseBase
from django.utils.encoding import force_bytes
from py_zipkin.zipkin import zipkin_span

# Set up Django for logging and stuff, it has to be done before importing django parts in handler
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "settings.development")  # noqa
django.setup()  # noqa


DEFAULT_HEADERS = (
    ('Cache-Control', 'no-cache'),
)
CORS_HEADER = (
    ('Access-Control-Allow-Origin', '*'),
)
ASYNC_SERVICE_NAME = '{}-async'.format(settings.SERVICE_NAME)

HANDLERS = dict()

logger = logging.getLogger(__name__)


def application(environ, start_response):
    from apps.core import zipkin
    from apps.core.helpers import import_class, set_tracing_attrs

    # Get and initialize if needed defined offload handler
    offload_handler = environ.get('OFFLOAD_HANDLER')

    if offload_handler not in HANDLERS:
        handler = import_class(offload_handler)()
        HANDLERS[offload_handler] = handler
    else:
        handler = HANDLERS[offload_handler]

    request = WSGIRequest(environ)
    zipkin_attrs = zipkin.extract_zipkin_attr(environ)
    set_tracing_attrs(zipkin_attrs)

    if zipkin_attrs.is_sampled:
        with zipkin_span(
            service_name=ASYNC_SERVICE_NAME,
            span_name='{0} {1}'.format(request.method, force_bytes(request.path)),
            zipkin_attrs=zipkin_attrs,
            transport_handler=zipkin.transport_handler,
            host='127.0.0.1',
            port=443,
        ) as zipkin_context:
            response = handler.application(request)
            binary_annotations = zipkin.get_binary_annotations(request, response)
            binary_annotations['offload_handler'] = offload_handler
            zipkin_context.update_binary_annotations(
                binary_annotations
            )
    else:
        response = handler.application(request)

    if not isinstance(response, HttpResponseBase):
        return response

    for k, v in DEFAULT_HEADERS:
        response[k] = v

    # If we're dealing with cross origin request, add necessary headers
    if environ.get('HTTP_ORIGIN'):
        for k, v in CORS_HEADER:
            response[k] = v

    http_status = '%s %s' % (response.status_code, response.reason_phrase)
    start_response(http_status, list(response.items()))
    return response
