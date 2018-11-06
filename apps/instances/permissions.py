# coding=UTF8
from django.conf import settings
from rest_framework.permissions import SAFE_METHODS, BasePermission

from apps.billing.permissions import AdminInGoodStanding
from apps.instances.models import Instance


class InstanceAccessAdminInGoodStanding(AdminInGoodStanding):
    def has_permission(self, request, view):
        if request.method not in SAFE_METHODS:
            return super().has_permission(request, view)
        return True


class InstanceLocationMatch(BasePermission):
    def has_object_permission(self, request, view, obj):
        if request.method not in SAFE_METHODS:
            return obj.location == settings.LOCATION
        return True


class ProtectInstanceAccess(BasePermission):
    """
    Only owner should have full rights to their instance.
    """

    def has_object_permission(self, request, view, obj):
        # Always allow retrieve - it's filtered out by queryset anyway
        is_read = request.method in SAFE_METHODS
        action = getattr(view, 'action', None)

        if action is not None:
            is_read = action == 'retrieve'
        if is_read or not isinstance(obj, Instance):
            return True
        # Owner should have unlimited access
        if request.user.is_authenticated:
            if request.user.is_role_satisfied(obj, 'owner'):
                return True

            # Only full role should be able to update instances, but not delete them
            is_update = request.method not in SAFE_METHODS
            if action is not None:
                is_update = action in ('update', 'partial_update')

            if is_update and request.user.is_role_satisfied(obj, 'full'):
                return True
        return False
