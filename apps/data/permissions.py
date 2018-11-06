# coding=UTF8
from rest_framework.permissions import BasePermission

from apps.data.models import DataObject, Klass
from apps.users.models import Membership


class HasKlassCreateObjectPermission(BasePermission):
    """
    Allows access to create endpoints when klass has CREATE_OBJECTS permission for others or current user's group.
    """

    def has_permission(self, request, view):
        klass = view.klass
        if view.action == 'create':
            if klass.other_permissions >= Klass.PERMISSIONS.CREATE_OBJECTS:
                return True

            return (request.auth_user and klass.group_permissions >= Klass.PERMISSIONS.CREATE_OBJECTS and
                    Membership.objects.filter(user=request.auth_user.id, group=klass.group_id).exists())
        return False

    def has_object_permission(self, request, view, obj):
        return False


class HasKlassReadPermission(BasePermission):
    """
    Allows access to non-create endpoints when klass has READ permission for others or current user's group.
    """

    def has_permission(self, request, view):
        klass = view.klass
        if view.action != 'create':
            if klass.other_permissions >= Klass.PERMISSIONS.READ:
                return True

            return (request.auth_user is not None and
                    klass.group_permissions >= Klass.PERMISSIONS.READ and
                    Membership.objects.filter(user=request.auth_user.id, group=klass.group_id).exists())
        return False


class ProtectUserProfileKlass(BasePermission):
    """
    Disallow deletion of User Profile klass.
    """

    def has_object_permission(self, request, view, obj):
        if obj.is_user_profile and view.action == 'destroy':
            return False
        return True


class ProtectUserProfileDataObject(BasePermission):
    """
    Disallow manual creation or deletion of User Profile data object.
    """

    def has_permission(self, request, view):
        if view.klass.is_user_profile and view.action == 'create':
            return False
        return True

    def has_object_permission(self, request, view, obj):
        if view.klass.is_user_profile and view.action == 'destroy':
            return False
        return True


class HasDataObjectPermission(BasePermission):
    """
    Allows access only when DO has write/full when action is update/delete.
    """

    def has_object_permission(self, request, view, obj):
        if view.action in ('update', 'partial_update'):
            min_permission = DataObject.PERMISSIONS.WRITE
        elif view.action == 'destroy':
            min_permission = DataObject.PERMISSIONS.FULL
        else:
            # Allow retrieving by default as DOs user don't have access to are filtered out anyway.
            return view.action == 'retrieve'

        user_permission = max(DataObject.PERMISSIONS.NONE, obj.other_permissions)
        if request.auth_user:
            if obj.owner == request.auth_user:
                user_permission = max(user_permission, obj.owner_permissions)

            if obj.group_permissions > user_permission and obj.group_id in request.auth_user.get_group_ids():
                user_permission = obj.group_permissions

        obj._user_permission = user_permission
        return user_permission >= min_permission
