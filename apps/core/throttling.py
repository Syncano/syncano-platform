# coding=UTF8
from rest_framework.throttling import AnonRateThrottle as _AnonRateThrottle
from rest_framework.throttling import ScopedRateThrottle as _ScopedRateThrottle
from rest_framework.throttling import UserRateThrottle as _UserRateThrottle

from apps.core.mixins import AllowStaffRateThrottleMixin, FastThrottleMixin


class AnonRateThrottle(AllowStaffRateThrottleMixin, FastThrottleMixin, _AnonRateThrottle):
    def get_cache_key(self, request, view):
        if request.user.is_authenticated or getattr(request, 'auth', None):
            return None  # Only throttle unauthenticated requests

        return self.cache_format % {
            'scope': self.scope,
            'ident': self.get_ident(request)
        }


class AdminRateThrottle(AllowStaffRateThrottleMixin, FastThrottleMixin, _UserRateThrottle):
    def get_cache_key(self, request, view):
        if not request.user.is_authenticated or getattr(request, 'instance', None):
            return None  # Only throttle authorized admins outside of instance

        return self.cache_format % {
            'scope': self.scope,
            'ident': request.user.pk
        }


class ScopedRateThrottle(AllowStaffRateThrottleMixin, _ScopedRateThrottle):
    pass
