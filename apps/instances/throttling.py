# coding=UTF8
from rest_framework.throttling import SimpleRateThrottle

from apps.billing.models import AdminLimit
from apps.core.mixins import AllowStaffRateThrottleMixin, FastThrottleMixin


class InstanceBasedRateThrottle(AllowStaffRateThrottleMixin, FastThrottleMixin, SimpleRateThrottle):
    """
    Limits the rate of API calls that may be made on a specific instance.
    """

    def get_cache_key(self, request, view):
        if not getattr(request, 'instance', None):
            return None  # Only throttle requests within instance

        return self.cache_format % {
            'scope': self.scope,
            'ident': request.instance.pk
        }


class InstanceRateThrottle(InstanceBasedRateThrottle):
    """
    Limits the rate of API calls that may be made on a specific instance based on per plan dynamic rate.
    """

    # Setting rate so we got something that passes later on, only using duration (resolution) part from it
    rate = '1/second'

    def get_instance_rate(self, request, view):
        return AdminLimit.get_for_admin(request.instance.owner_id).get_rate()

    def allow_request(self, request, view):
        instance = getattr(request, 'instance', None)
        if not instance:
            return True
        self.num_requests = self.get_instance_rate(request, view)
        return super().allow_request(request, view)
