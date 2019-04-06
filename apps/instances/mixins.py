# coding=UTF8
import re

from django.conf import settings

from apps.admins.models import Admin
from apps.core.exceptions import ModelNotFound
from apps.core.helpers import Cached
from apps.instances.exceptions import InstanceLocationMismatch, InstanceVersionMismatch
from apps.instances.helpers import set_current_instance

from .models import Instance

INSTANCE_NAME_REGEX = re.compile('^[a-z0-9-_]{,64}$')


class InstanceBasedMixin:
    def initialize_request(self, request, *args, **kwargs):
        instance = getattr(request, 'instance', kwargs.get('instance', None))

        if not isinstance(instance, Instance):
            value = instance.lower()
            instance = None
            if INSTANCE_NAME_REGEX.match(value):
                try:
                    instance = Cached(Instance, kwargs=dict(name=value)).get()
                except Instance.DoesNotExist:
                    pass

        if instance is not None:
            if getattr(request, 'instance', None) is None and request.META.get('HTTP_HOST_TYPE') != 'hosting':
                admin = Cached(Admin, kwargs={'id': instance.owner_id}).get()
                admin.update_last_access()

            self.kwargs['instance'] = instance
            set_current_instance(instance)

            if instance.version > 1:
                request.error = InstanceVersionMismatch()
            if instance.location != settings.LOCATION:
                request.error = InstanceLocationMismatch()

        request.instance = instance
        return super().initialize_request(request, *args, **kwargs)

    def initial(self, request, *args, **kwargs):
        if not request.instance:
            raise ModelNotFound(Instance)
        if getattr(request, 'error', None):
            raise request.error
        return super().initial(request, *args, **kwargs)
