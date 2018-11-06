# coding=UTF8
from rest_framework.permissions import BasePermission


class AllowApiKeyRenderAccess(BasePermission):
    """
    Disallow deletion of User Profile klass.
    """

    def has_object_permission(self, request, view, obj):
        return request.auth is not None and view.action == 'render'
