# coding=UTF8
from rest_framework.permissions import BasePermission

from apps.channels.exceptions import CustomPublishNotAllowed, RoomRequired
from apps.channels.models import Channel
from apps.core.permissions import CheckAclPermissionBase
from apps.users.models import Membership


def _channel_has_subscribe_permission(channel, request):
    if channel.other_permissions >= Channel.PERMISSIONS.SUBSCRIBE:
        return True

    return (request.auth_user and channel.group_permissions >= Channel.PERMISSIONS.SUBSCRIBE and
            Membership.objects.filter(user=request.auth_user.id, group=channel.group_id).exists())


class HasPublishPermission(BasePermission):
    """
    Allows access to publish to channel when it has PUBLISH permission for others or current user's group.
    """

    def has_object_permission(self, request, view, obj):
        if obj.other_permissions >= Channel.PERMISSIONS.PUBLISH:
            return True

        return (request.auth_user and obj.group_permissions >= Channel.PERMISSIONS.PUBLISH and
                Membership.objects.filter(user=request.auth_user.id, group=obj.group_id).exists())


class HasSubscribePermission(BasePermission):
    """
    Allows access to channel that has SUBSCRIBE permission for others or current user's group.
    """

    def has_object_permission(self, request, view, obj):
        return _channel_has_subscribe_permission(obj, request)


class HasChannelSubscribePermission(BasePermission):
    """
    Allows access to history when channel has SUBSCRIBE permission for others or current user's group.
    """

    def has_permission(self, request, view):
        return _channel_has_subscribe_permission(view.channel, request)


class EnsureChannelRoom(BasePermission):
    def has_permission(self, request, view):
        if view.channel.type == Channel.TYPES.SEPARATE_ROOMS and view.room is None:
            raise RoomRequired()
        return True


class EnsureChannelCustomPublish(BasePermission):
    def has_object_permission(self, request, view, obj):
        if isinstance(obj, Channel) and not obj.custom_publish:
            raise CustomPublishNotAllowed()
        return True


class CheckChangeAclPermission(CheckAclPermissionBase):
    def has_permission(self, request, view):
        return self.has_parent_permission(request, view, permission=Channel.SUBSCRIBE_PERMISSION)


class ProtectBuiltinChannel(BasePermission):
    """
    Protect builtin channels - default and eventlog.
    """

    def has_object_permission(self, request, view, obj):
        if not isinstance(obj, Channel):
            return True
        if obj.name == Channel.DEFAULT_NAME and view.action == 'destroy':
            return False
        if obj.name == Channel.EVENTLOG_NAME and view.action in ('destroy', 'publish'):
            return False
        return True
