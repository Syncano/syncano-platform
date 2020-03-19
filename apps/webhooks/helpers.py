# coding=UTF8
from django.core.files.uploadedfile import UploadedFile
from django.http import QueryDict

ALLOWED_META_KEYS = {'PATH_INFO', 'REQUEST_METHOD'}
DISALLOWED_META_KEYS = {
    'HTTP_X_FORWARDED_FOR',
    'HTTP_X_FORWARDED_PROTO',
    'HTTP_X_FORWARDED_PORT',
    'HTTP_X_FORWARDED_HOST',
    'HTTP_X_ORIGINAL_FORWARDED_FOR',
    'HTTP_X_REAL_IP',
    'HTTP_X_API_KEY',
    'HTTP_X_USER_KEY',
    'HTTP_X_SCHEME',
    'HTTP_AUTHORIZATION',
    'HTTP_HOST_TYPE',
    'HTTP_CONNECTION',
    'HTTP_CF_VISITOR',
    'HTTP_CF_RAY',
    'HTTP_CF_CONNECTING_IP',
    'HTTP_CDN_LOOP',
}


def strip_meta_from_uwsgi_info(request_meta):
    """Strips request_meta from unnecessary information."""
    stripped = {}
    for key in request_meta:
        if key in ALLOWED_META_KEYS or (key not in DISALLOWED_META_KEYS and key.startswith('HTTP_')):
            stripped[key] = request_meta[key]

    ip_header = request_meta.get('HTTP_X_FORWARDED_FOR', request_meta.get('HTTP_X_REAL_IP',
                                 request_meta.get('REMOTE_ADDR', '')))
    stripped['REMOTE_ADDR'] = ip_header.split(',', 2)[0]
    return stripped


def prepare_payload_data(request):
    post_data = request.data
    if isinstance(post_data, QueryDict):
        post_data = post_data.dict()

    if isinstance(post_data, dict):
        for key, value in post_data.items():
            if isinstance(value, UploadedFile):
                post_data[key] = value.read()

        for key in ('_api_key', '_user_key'):
            post_data.pop(key, None)

    get_data = request.query_params.dict()
    for key in ('api_key', 'apikey'):
        get_data.pop(key, None)

    data = {
        'POST': post_data,
        'GET': get_data
    }
    return data
