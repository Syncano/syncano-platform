# coding=UTF8
from django.core.exceptions import ObjectDoesNotExist
from rest_framework.permissions import BasePermission

from apps.admins.models import Role
from apps.core.permissions import ModelPermissions

HIERARCHY = Role.ROLE_HIERARCHY


class AdminHasPermissions(ModelPermissions):
    def is_valid_request(self, request):
        return request.user.is_authenticated and hasattr(request, 'instance')

    def get_model_permissions(self, request, permission_config):
        admin_config = permission_config.get('admin')

        if admin_config:
            try:
                role_name = request.user.get_role_name(request.instance)
                # Try all roles in hierarchy.
                # E.g. if user has write role and there are no write-specific permissions, fall back to read role.
                for role_name in HIERARCHY[HIERARCHY.index(role_name):]:
                    if role_name in admin_config:
                        return admin_config[role_name]
            except ObjectDoesNotExist:
                pass
        # Return empty set otherwise
        return set()


class ProtectOwnerAccess(BasePermission):
    """
    Disallow tampering with owner role.
    """

    def has_object_permission(self, request, view, obj):
        # Always allow retrieve - it's filtered out by queryset anyway
        if view.action == 'retrieve':
            return True
        # Disallow everything else if object is an instance owner's role
        if request.instance.owner_id == obj.admin_id:
            return False
        return True


class AllowSelfRoleDeletion(BasePermission):
    """
    Allow deleting own role.
    """

    def has_object_permission(self, request, view, obj):
        if view.action == 'destroy':
            return request.user.is_authenticated and obj.admin_id == request.user.id
        return False
