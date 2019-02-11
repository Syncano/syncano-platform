# coding=UTF8
from django.conf import settings
from django.http import Http404

from apps.core.helpers import Cached
from apps.hosting.v1_1.views import HostingView
from apps.instances.models import Instance


class HostingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

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

        return HostingView.as_view()(request, **kwargs)
