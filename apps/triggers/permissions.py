# coding=UTF8
from rest_framework.permissions import BasePermission


class ProtectTriggerAccess(BasePermission):
    """
    Disallow editing triggers that are bound to socket.
    """
    allowed_actions = ('retrieve', 'emit',)

    def has_object_permission(self, request, view, obj):
        return getattr(obj, 'socket_id', None) is None or view.action in self.allowed_actions
