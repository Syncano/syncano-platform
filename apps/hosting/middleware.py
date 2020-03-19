# coding=UTF8
import os.path
import re

from django.conf import settings
from django.http import Http404, HttpResponse
from rest_framework import status

from apps.core.helpers import Cached
from apps.hosting.v1_1.views import HostingView
from apps.instances.models import Instance

ACME_REGEX = re.compile(r'^/.well-known/acme-challenge/(?P<acme_key>[-_a-zA-Z0-9]+)$')


class HostingMiddleware:
    acme_thumb = 'acme_thumb'
    acme_thumb_file = '/acme/config/account.thumb'

    def __init__(self, get_response):
        self.get_response = get_response

        if os.path.isfile(self.acme_thumb_file):
            with open(self.acme_thumb_file) as f:
                self.acme_thumb = f.read().strip()

    def __call__(self, request):
        host = request.META.get('HTTP_HOST')
        if not host or request.META.get('HTTP_HOST_TYPE') != 'hosting':
            return self.get_response(request)

        host = host.split(':', 1)[0]
        is_custom_domain = not host.endswith(settings.HOSTING_DOMAIN)

        if is_custom_domain:
            try:
                instance = Cached(Instance, kwargs={'domains__contains': [host], 'location': settings.LOCATION}).get()
            except Instance.DoesNotExist:
                raise Http404()
        else:
            instance = host.split('.')[0]
            # Check if we're dealing with: <prefix>--<instance_name>
            domain_data = instance.rsplit('--', 1)
            if len(domain_data) == 2:
                host, instance = domain_data
            else:
                host = '_default'

        kwargs = {
            'domain': host,
            'instance': instance
        }

        if request.path == '/%s/' % settings.HOSTING_TOKEN:
            return HttpResponse(settings.LOCATION, status=status.HTTP_200_OK, content_type='text/plain')

        acme_res = ACME_REGEX.match(request.path)
        if acme_res is not None:
            return HttpResponse('{}.{}'.format(acme_res.group('acme_key'), self.acme_thumb), status=status.HTTP_200_OK,
                                content_type='text/plain')

        return HostingView.as_view()(request, **kwargs)
