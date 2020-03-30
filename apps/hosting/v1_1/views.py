# coding=UTF8
import base64
from string import Template

from django.conf import settings
from django.http import Http404, HttpResponse, HttpResponseNotFound
from django.utils.encoding import escape_uri_path, force_bytes, iri_to_uri
from rest_framework import generics, permissions, status
from rest_framework.decorators import detail_route
from rest_framework.response import Response
from rest_framework.serializers import Serializer
from rest_framework.viewsets import ModelViewSet
from rest_framework_extensions.mixins import DetailSerializerMixin

from apps.admins.permissions import AdminHasPermissions
from apps.billing.permissions import OwnerInGoodStanding
from apps.core.authentication import AUTHORIZATION_HEADER
from apps.core.exceptions import ModelNotFound
from apps.core.helpers import Cached, get_cur_loc_env, glob, redis, run_api_view
from apps.core.mixins.views import AtomicMixin, NestedViewSetMixin
from apps.hosting.exceptions import ValidCNameMissing
from apps.hosting.models import Hosting, HostingFile
from apps.hosting.negotiations import IgnoreClientContentNegotiation
from apps.hosting.permissions import ProtectHostingAccess
from apps.hosting.v1_1.serializers import (
    HostingDetailSerializer,
    HostingFileDetailSerializer,
    HostingFileSerializer,
    HostingSerializer
)
from apps.instances.mixins import InstanceBasedMixin


class HostingViewSet(AtomicMixin,
                     InstanceBasedMixin,
                     DetailSerializerMixin,
                     ModelViewSet):
    model = Hosting
    queryset = Hosting.objects.all()
    serializer_class = HostingSerializer
    serializer_detail_class = HostingDetailSerializer
    hosting_serializer_class = HostingSerializer
    permission_classes = (
        AdminHasPermissions,
        OwnerInGoodStanding,
        ProtectHostingAccess,
    )

    def initial(self, request, *args, **kwargs):
        self.lock = None

        if request.instance and request.method not in permissions.SAFE_METHODS:
            # Make a lock to avoid deadlocks
            self.lock = redis.lock(self.model.get_instance_lock_key(request.instance),
                                   timeout=settings.LOCK_TIMEOUT)
            self.lock.acquire()
        return super().initial(request, *args, **kwargs)

    def finalize_response(self, request, response, *args, **kwargs):
        if self.lock:
            self.lock.release()
        return super().finalize_response(request, response, *args, **kwargs)

    @detail_route(methods=['POST'], serializer_detail_class=Serializer)
    def set_default(self, request, *args, **kwargs):
        hosting = self.get_object()

        serializer = self.hosting_serializer_class(hosting,
                                                   data={},
                                                   partial=True,
                                                   context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)

        if not hosting.is_default:
            # remove old default;
            try:
                old_default_hosting = Hosting.objects.filter(is_default=True).get()
                old_default_hosting.is_default = False
                old_default_hosting.save(update_fields=['is_default'])
            except Hosting.DoesNotExist:
                pass

            # set new default;
            serializer.save(is_default=True)

        return Response(serializer.data, status=status.HTTP_200_OK)

    @detail_route(methods=['POST'], serializer_detail_class=Serializer)
    def enable_ssl(self, request, *args, **kwargs):
        hosting = self.get_object()
        serializer = self.hosting_serializer_class(hosting,
                                                   data={},
                                                   partial=True,
                                                   context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)

        if hosting.ssl_status != Hosting.SSL_STATUSES.ON:
            if not hosting.get_cname():
                raise ValidCNameMissing()
            serializer.save(ssl_status=Hosting.SSL_STATUSES.CHECKING)

        return Response(serializer.data, status=status.HTTP_200_OK)


class HostingFileViewSet(AtomicMixin, InstanceBasedMixin, NestedViewSetMixin, DetailSerializerMixin, ModelViewSet):
    model = HostingFile
    queryset = HostingFile.objects.all()
    serializer_class = HostingFileSerializer
    serializer_detail_class = HostingFileDetailSerializer


class HostingView(InstanceBasedMixin, generics.GenericAPIView):
    """
    View used for getting actual Hosting File and returning internal redirect path to it.
    Used in combination with HostingMiddleware.
    """
    DEFAULT_FILE = 'index.html'
    DEFAULT_404_FILE = '404.html'

    EMPTY_INDEX_IFRAME = 'https://syncano.io/#/hosting-intro/'
    EMPTY_404_IFRAME = 'https://syncano.io/#/404/'
    EMPTY_404_KEY = 'empty'

    DEFAULT_CONTENT_TMPL = Template(
        '<!doctype html><html>'
        '<head><title>Syncano Hosting</title>'
        '<style type="text/css">'
        'body, html{margin: 0; padding: 0; height: 100%; overflow: hidden;}'
        'iframe{width: 100%; height: 100%; border:0}'
        '#content{position:absolute; left: 0; right: 0; bottom: 0; top: 0px;}</style></head>'
        '<body><div id="content"><iframe src="$iframe"></iframe>'
        '</div></body>'
        '</html>'
    )

    content_negotiation_class = IgnoreClientContentNegotiation
    throttle_classes = ()
    permission_classes = (permissions.AllowAny,)
    authentication_classes = ()

    @classmethod
    def get_accel_redirect(cls, request, url, url_404, query):
        bucket, instance_id, hosting_id, path = cls.split_url(url)
        _, _, _, path_404 = cls.split_url(url_404)
        redirect_url = '/internal_redirect/{}/{}/{}/{}/{}/{}'.format(
            get_cur_loc_env('STORAGE', 'local'), bucket, instance_id, hosting_id, path_404, path)

        if query:
            redirect_url += '?%s' % query

        return redirect_url

    @classmethod
    def get_hosting_search_kwargs(cls, domain):
        if domain == '_default':
            return {'is_default': True, 'is_active': True}
        return {'domains__contains': [domain], 'is_active': True}

    @classmethod
    def split_url(cls, url):
        if url == 'empty':
            return None, None, None, 'empty'

        if url.startswith(settings.MEDIA_URL):
            url == url[len(settings.MEDIA_URL):]
        else:
            _, url = url.split('//', 1)
        if get_cur_loc_env('STORAGE') == 'gcs':
            _, url = url.split('/', 1)
        return url.split('/', 3)

    def create_404_response(self):
        return HttpResponseNotFound(
            self.DEFAULT_CONTENT_TMPL.substitute(iframe=self.EMPTY_404_IFRAME),
            content_type='text/html'
        )

    def handle_exception(self, exc):
        if isinstance(exc, (Http404, ModelNotFound)):
            return self.create_404_response()
        return super().handle_exception(exc)

    def check_auth(self, request, hosting):
        # Check for valid basic auth header
        if AUTHORIZATION_HEADER in request.META:
            auth = request.META.pop(AUTHORIZATION_HEADER).split()

            if len(auth) == 2 and auth[0].lower() == 'basic':
                uname, passwd = base64.b64decode(force_bytes(auth[1])).decode().split(':', 1)
                return hosting.check_auth(uname, passwd)
        return False

    def get(self, request, *args, **kwargs):
        return self.process(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        return self.process(request, *args, **kwargs)

    def patch(self, request, *args, **kwargs):
        return self.process(request, *args, **kwargs)

    def put(self, request, *args, **kwargs):
        return self.process(request, *args, **kwargs)

    def delete(self, request, *args, **kwargs):
        return self.process(request, *args, **kwargs)

    def options(self, request, *args, **kwargs):
        return Response(status=status.HTTP_200_OK)

    def process(self, request, *args, **kwargs):
        path = escape_uri_path(request.path)

        try:
            hosting = Cached(
                Hosting,
                kwargs=self.get_hosting_search_kwargs(domain=kwargs.get('domain'))
            ).get()
        except Hosting.DoesNotExist:
            return self.create_404_response()

        if hosting.auth and not self.check_auth(request, hosting):
            # Either they did not provide an authorization header or
            # something in the authorization attempt failed. Send a 401
            # back to them to ask them to authenticate.
            response = HttpResponse(status=status.HTTP_401_UNAUTHORIZED)
            response['WWW-Authenticate'] = 'Basic realm="Restricted"'
            return response

        for pattern, socket in hosting.config.get('sockets_mapping', []):
            if glob(pattern, path):
                request.version = 'v2'
                return run_api_view('socket-endpoint-endpoint', (request.instance.name, socket), request)

        if request.method != 'GET':
            self.http_method_not_allowed(request)

        # Strip '/' prefix for further processing.
        if path.endswith('/'):  # jekyll like: '/about/' we should find path '/about/index.html' in such case;
            path = '{}{}'.format(path, self.DEFAULT_FILE)
        path = path.lstrip('/')
        query = iri_to_uri(request.META.get('QUERY_STRING', ''))

        try:
            hosting_file = HostingFile.get_file(hosting=hosting, path=path)
            return self.get_accel_response(request,
                                           Hosting.get_storage().internal_url(hosting_file.file_object.name),
                                           self.EMPTY_404_KEY,
                                           query)
        except HostingFile.DoesNotExist:
            return self.handle_missing_file(request, hosting, query, path)

    def handle_missing_file(self, request, hosting, query, path):
        # Return default web pages if path is empty and hosting has no files.
        if hosting.is_empty and path == self.DEFAULT_FILE:
            return HttpResponse(
                self.DEFAULT_CONTENT_TMPL.substitute(iframe=self.EMPTY_INDEX_IFRAME),
                content_type='text/html'
            )

        # Return index.html if browser router is enabled.
        if hosting.is_browser_router_enabled:
            try:
                hosting_file = HostingFile.get_file(hosting=hosting, path=self.DEFAULT_FILE)
            except HostingFile.DoesNotExist:
                pass
            else:
                return self.get_accel_response(request,
                                               url=Hosting.get_storage().internal_url(hosting_file.file_object.name),
                                               url_404=self.EMPTY_404_KEY,
                                               query=query)

        # Check for custom 404.
        try:
            hosting_file = HostingFile.get_file(hosting=hosting, path=self.DEFAULT_404_FILE)
        except HostingFile.DoesNotExist:
            return self.create_404_response()

        url_404 = Hosting.get_storage().internal_url(hosting_file.file_object.name),

        return self.get_accel_response(request,
                                       url='{}/{}'.format(url_404.rsplit('/', 1)[0], path),
                                       url_404=url_404,
                                       query=query)

    def get_accel_response(self, request, url, url_404, query):
        response = HttpResponse()
        response['X-Accel-Redirect'] = self.get_accel_redirect(request, url, url_404, query)
        return response

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)

        if not getattr(response, 'is_rendered', True) and callable(getattr(response, 'render', None)):
            response = response.render()
        return response
