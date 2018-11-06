# coding=UTF8
from rest_framework.permissions import BasePermission

from apps.core.permissions import CheckAclPermissionBase
from apps.users.models import Group


class HasUser(BasePermission):
    """
    Allows access only when user is authenticated.
    """

    def has_permission(self, request, view):
        return request.auth_user is not None


class IsMembershipForCurrentUser(BasePermission):
    """
    Allows access only when looking up current user's groups.
    """

    def has_permission(self, request, view):
        return request.auth_user is not None and request.auth_user.id == view.user.id


class HasCreateUserPermission(BasePermission):
    """
    Allows access only when Api Key allows creating a new user.
    """

    def has_permission(self, request, view):
        return view.action == 'create' and request.auth.allow_user_create


class HasCreateGroupPermission(BasePermission):
    """
    Allows access only when Api Key allows creating a new group.
    """

    def has_permission(self, request, view):
        return view.action == 'create' and request.auth.allow_group_create


class CheckGroupMembershipAclPermission(CheckAclPermissionBase):
    def has_permission(self, request, view):
        perm = None
        if view.action == 'create':
            perm = Group.ADD_USER_PERMISSIONS
        elif view.action == 'destroy':
            perm = Group.REMOVE_USER_PERMISSIONS
        return self.has_parent_permission(request, view, permission=perm)
