# coding=UTF8
from rest_framework.permissions import BasePermission


class AllowedToClearCache(BasePermission):
    """
    Allow clearing cache only users with write permissions to instance.
    """

    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.is_role_satisfied(request.instance, 'write')


class AllowEndpointAction(BasePermission):
    """
    Allow all endpoint actions as they are proxied to data permission checks.
    """

    def has_permission(self, request, view):
        return view.action.startswith('endpoint_')
