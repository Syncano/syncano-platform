# coding=UTF8
from rest_framework import permissions
from rest_framework.permissions import BasePermission

from apps.core.permissions import ModelPermissions


class ApiKeyHasPermissions(ModelPermissions):
    def is_valid_request(self, request):
        return request.auth

    def get_model_permissions(self, request, permission_config):
        return permission_config.get('api_key', set())


class IsApiKeyAccess(BasePermission):
    """
    Allows access only when either api key is used for authentication.
    """

    def has_permission(self, request, view):
        return request.auth is not None


class IsApiKeyIgnoringAcl(BasePermission):
    """
    Allows access only when ApiKey has ignore_acl flag set.

    Expects that check for request.auth was already done. E.g. by IsApiKeyAccess.
    """

    def has_permission(self, request, view):
        return request.auth.ignore_acl

    def has_object_permission(self, request, view, obj):
        return request.auth.ignore_acl


class IsApiKeyAllowingAnonymousRead(BasePermission):
    """
    Allows access only when ApiKey has allow_anonymous_read flag set.
    """

    def has_permission(self, request, view):
        if not request.auth or request.method not in permissions.SAFE_METHODS:
            return False

        return request.auth.allow_anonymous_read

    def has_object_permission(self, request, view, obj):
        return self.has_permission(request, view)
