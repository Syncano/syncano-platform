# coding=UTF8
import random
import struct

import requests
from django.conf import settings
from py_zipkin.util import generate_random_64bit_string
from py_zipkin.zipkin import ZipkinAttrs

try:
    # try to import uwsgi first as that module is not be available outside of uwsgi context (e.g. during tests)
    import uwsgi
except ImportError:
    uwsgi = None

ZIPKIN_TRANSPORT_URL = 'http://{}:9411/api/v1/spans'.format(settings.ZIPKIN_ADDR)


def transport_handler(encoded_span):
    try:
        requests.post(
            ZIPKIN_TRANSPORT_URL,
            data=encoded_span,
            headers={'Content-Type': 'application/x-thrift'},
            timeout=settings.ZIPKIN_TIMEOUT,
        )
    except requests.RequestException:
        if settings.ZIPKIN_RAISE:
            raise


def get_trace_id(request):
    """
    Gets the trace id based on a request.
    """
    if 'X-B3-TRACEID' in request.META:
        trace_id = _convert_signed_hex(request.META['X-B3-TRACEID'])
        # Tolerates 128 bit X-B3-TraceId by reading the right-most 16 hex
        # characters (as opposed to overflowing a U64 and starting a new trace).
        trace_id = trace_id[-16:]
    else:
        trace_id = generate_random_64bit_string()

    return trace_id


def _convert_signed_hex(s):
    """
    Takes a signed hex string that begins with '0x' and converts it to
    a 16-character string representing an unsigned hex value.
    Examples:
        '0xd68adf75f4cfd13' => 'd68adf75f4cfd13'
        '-0x3ab5151d76fb85e1' => 'c54aeae289047a1f'
    """
    if s.startswith('0x') or s.startswith('-0x'):
        s = '{0:x}'.format(struct.unpack('Q', struct.pack('q', int(s, 16)))[0])
    return s.zfill(16)


def should_sample_as_per_zipkin_tracing_sampling(tracing_sampling):
    """
    Calculate whether the request should be traced as per tracing percent.

    :param tracing_sampling: value between 0.0 to 1.0
    :type tracing_sampling: float
    :returns: boolean whether current request should be sampled.
    """
    return random.random() < tracing_sampling


def is_request_sampled(request):
    """
    Determine if zipkin should be tracing
    1) If not, check if specific sampled header is present in the request.
    2) If not, Use a tracing percent (default: 0.5%) to decide.
    """
    if 'HTTP_X_B3_SAMPLED' in request.META:
        return request.META['HTTP_X_B3_SAMPLED'] == '1'
    return should_sample_as_per_zipkin_tracing_sampling(settings.TRACING_SAMPLING)


def create_zipkin_attr_from_request(request):
    """
    Create ZipkinAttrs object from a request with sampled flag as True.
    """
    trace_id = get_trace_id(request)
    span_id = request.META.get('HTTP_X_B3_SPANID', generate_random_64bit_string())
    parent_span_id = request.META.get('HTTP_X_B3_PARENTSPANID', None)
    flags = request.META.get('HTTP_X_B3_FLAGS', '0')
    is_sampled = is_request_sampled(request)

    return ZipkinAttrs(
        trace_id=trace_id,
        span_id=span_id,
        parent_span_id=parent_span_id,
        flags=flags,
        is_sampled=is_sampled,
    )


def create_headers_from_zipkin_attrs(zipkin_attrs):
    """
    Create headers dict from ZipkinAttrs object for use in requests.
    """
    if not zipkin_attrs:
        return {}
    return {
        'x-b3-traceid': zipkin_attrs.trace_id,
        'x-b3-flags': zipkin_attrs.flags,
        'x-b3-spanid': zipkin_attrs.span_id,
        'x-b3-sampled': '1' if zipkin_attrs.is_sampled else '0',
    }


def extract_zipkin_attr(data):
    """
    Create ZipkinAttrs object from a dict.
    """
    if not data or 'x-b3-sampled' not in data:
        return ZipkinAttrs('', '', '', '0', False)
    return ZipkinAttrs(
        trace_id=data['x-b3-traceid'],
        span_id=generate_random_64bit_string(),
        parent_span_id=data['x-b3-spanid'],
        flags=data['x-b3-flags'],
        is_sampled=data['x-b3-sampled'],
    )


def propagate_uwsgi_params(zipkin_attrs):
    if uwsgi is not None:
        for k, v in create_headers_from_zipkin_attrs(zipkin_attrs).items():
            uwsgi.add_var(k, v)


def get_binary_annotations(request, response):
    """
    Helper method for getting all binary annotations from the request.
    """
    annotations = {
        'http.method': request.method,
        'http.url': request.path,
        'http.status_code': str(getattr(response, 'status_code', '0')),
    }
    return annotations
