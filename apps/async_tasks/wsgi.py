# coding=UTF8
import gevent.monkey  # isort:skip

gevent.monkey.patch_all()  # noqa

import os  # isort:skip
import django  # isort:skip

# Set up Django for logging and stuff, it has to be done before importing django parts in handler
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "settings.development")  # noqa
django.setup()  # noqa

import logging

from django.conf import settings
from django.core.handlers.wsgi import WSGIRequest
from django.http.response import HttpResponseBase
from opencensus.trace import attributes_helper
from opencensus.trace import span as span_module

from apps.core.helpers import create_tracer, get_tracer_propagator

HTTP_HOST = attributes_helper.COMMON_ATTRIBUTES['HTTP_HOST']
HTTP_METHOD = attributes_helper.COMMON_ATTRIBUTES['HTTP_METHOD']
HTTP_PATH = attributes_helper.COMMON_ATTRIBUTES['HTTP_PATH']
HTTP_ROUTE = attributes_helper.COMMON_ATTRIBUTES['HTTP_ROUTE']
HTTP_URL = attributes_helper.COMMON_ATTRIBUTES['HTTP_URL']
HTTP_STATUS_CODE = attributes_helper.COMMON_ATTRIBUTES['HTTP_STATUS_CODE']
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
    from apps.core.helpers import import_class

    # Get and initialize if needed defined offload handler
    offload_handler = environ.get('OFFLOAD_HANDLER')

    if offload_handler not in HANDLERS:
        handler = import_class(offload_handler)()
        HANDLERS[offload_handler] = handler
    else:
        handler = HANDLERS[offload_handler]

    propagator = get_tracer_propagator()
    tracer = create_tracer(propagator.from_headers(environ))

    request = WSGIRequest(environ)

    with tracer.span(name='Async.' + str(request.path)) as span:
        response = handler.application(request)

        span.span_kind = span_module.SpanKind.SERVER
        span.add_attribute(
            attribute_key=HTTP_HOST,
            attribute_value=request.get_host())
        span.add_attribute(
            attribute_key=HTTP_METHOD,
            attribute_value=request.method)
        span.add_attribute(
            attribute_key=HTTP_PATH,
            attribute_value=str(request.path))
        span.add_attribute(
            attribute_key=HTTP_ROUTE,
            attribute_value=str(request.path))
        span.add_attribute(
            attribute_key=HTTP_URL,
            attribute_value=str(request.build_absolute_uri()))
        span.add_attribute(
            attribute_key=HTTP_STATUS_CODE,
            attribute_value=response.status_code)
        span.add_attribute(
            attribute_key='async.offload_handler',
            attribute_value=offload_handler)

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
