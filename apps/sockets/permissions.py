# coding=UTF8
from apps.core.permissions import CheckAclPermissionBase


class CheckEndpointAclPermission(CheckAclPermissionBase):
    """
    Check ACL for current action on object level if ACL is set.
    """

    def has_object_permission(self, request, view, obj):
        if not obj.acl:
            return True
        return self.has_object_level_permission(request, view, obj)
