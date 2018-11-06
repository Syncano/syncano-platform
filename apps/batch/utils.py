# coding=UTF8
import rapidjson as json
from django.conf import settings
from django.http import HttpResponseServerError
from django.test.client import FakePayload, RequestFactory
from django.urls import Resolver404, resolve

IGNORE_BODY_METHODS = ('GET', 'DELETE')
AUTH_KEYS = ('user', 'auth', 'auth_user', 'staff_user', 'instance')
HEADERS_TO_INCLUDE = ("HTTP_USER_AGENT", "HTTP_COOKIE")


class BatchRequestFactory(RequestFactory):
    """
    Extend the RequestFactory and update the environment variables for WSGI.
    """

    def _base_environ(self, **request):
        """
        Override the default values for the wsgi environment variables.
        """
        # This is a minimal valid WSGI environ dictionary, plus:
        # - HTTP_COOKIE: for cookie support,
        # - REMOTE_ADDR: often useful, see #8551.
        # See http://www.python.org/dev/peps/pep-3333/#environ-variables

        environ = {
            'HTTP_COOKIE': self.cookies.output(header='', sep='; '),
            'PATH_INFO': str('/'),
            'REMOTE_ADDR': str('127.0.0.1'),
            'REQUEST_METHOD': str('GET'),
            'SCRIPT_NAME': str(''),
            'SERVER_NAME': str('localhost'),
            'SERVER_PORT': str('8000'),
            'SERVER_PROTOCOL': str('HTTP/1.1'),
            'wsgi.version': (1, 0),
            'wsgi.url_scheme': str('http'),
            'wsgi.input': FakePayload(b''),
            'wsgi.errors': self.errors,
            'wsgi.multiprocess': True,
            'wsgi.multithread': True,
            'wsgi.run_once': False,
        }
        environ.update(self.defaults)
        environ.update(request)
        return environ


def get_response(request, **additional_kwargs):
    """
    Given a WSGI request, makes a call to a corresponding view
    function and returns the response.
    """
    # Get the view / handler for this request
    try:
        resolver_match = resolve(request.path_info)
    except Resolver404:
        return {'code': 404, 'content': 'Invalid endpoint specified.'}

    request.resolver_match = resolver_match
    view, args, kwargs = resolver_match
    kwargs.update(additional_kwargs)

    # Let the view do his task.
    try:
        resp = view(request, *args, **kwargs)
    except Exception as exc:
        resp = HttpResponseServerError(content=str(exc))

    # Convert HTTP response into simple dict type.
    response = {'code': resp.status_code}
    response_len = 0
    if getattr(resp, 'data', None):
        data = json.dumps(
            resp.data,
            number_mode=json.NM_NATIVE
        )
        response_len = len(data)
        data = json.RawJSON(data)
        if not settings.RESPONSE_ENCODED:
            data = resp.data
        response['content'] = data
    return response, response_len


def get_wsgi_request_object(request, method, url, headers, body):
    """
    Based on the given request parameters, constructs and returns the WSGI request object.
    """
    method = method.lower()
    # Add default content type.
    if 'CONTENT_TYPE' not in headers:
        headers['CONTENT_TYPE'] = 'application/json'
    content_type = headers['CONTENT_TYPE']

    headers.update({h: v for h, v in request.META.items() if h in HEADERS_TO_INCLUDE})

    # Get hold of request factory to construct the request.
    request_factory = BatchRequestFactory()
    request_provider = getattr(request_factory, method)

    wsgi_request = request_provider(url, data=None, secure=True,
                                    content_type=content_type, **headers)

    # Set Auth Keys
    for key in AUTH_KEYS:
        setattr(wsgi_request, key, getattr(request, key))

    wsgi_request.data = None
    if method not in IGNORE_BODY_METHODS and body:
        wsgi_request.data = body

    return wsgi_request
