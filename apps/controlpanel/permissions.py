# coding=UTF8
from rest_framework import permissions


class IsStaffUser(permissions.BasePermission):
    """
        Allow access only to admins with is_staff flag set,
        or users with valid STAFF_KEY set.
    """

    def has_permission(self, request, view):
        return (request.user and request.user.is_staff) or request.staff_user is not None
