# coding=UTF8
from rest_framework.permissions import BasePermission


class UserHasFullPermissions(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.is_role_satisfied(request.instance, "full")
