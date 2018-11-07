# coding=UTF8
from rest_framework.permissions import BasePermission


class HasDevicePermission(BasePermission):
    """
    Allows access only when instance user owns a device.
    """

    def has_object_permission(self, request, view, obj):
        if view.action == 'retrieve':
            # Devices are filtered out anyway.
            return True

        if request.auth_user:
            return obj.user == request.auth_user

        return False
