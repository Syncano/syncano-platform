# coding=UTF8
from rest_framework.permissions import BasePermission

from apps.core.exceptions import ModelNotFound
from apps.core.helpers import MetaEnum


class API_PERMISSIONS(MetaEnum):
    CREATE = 'create'
    READ = 'read'
    UPDATE = 'update'
    DELETE = 'delete'


FULL_PERMISSIONS = {API_PERMISSIONS.CREATE, API_PERMISSIONS.READ, API_PERMISSIONS.UPDATE, API_PERMISSIONS.DELETE}


class ModelPermissions(BasePermission):
    """
    Checks permissions based on a predefined permission set.
    Each Model permissions are checked against perms_map based on it's field PERMISSION_CONFIG.
    """

    perms_map = {
        'default': API_PERMISSIONS.READ,
        'detail': {
            'POST': API_PERMISSIONS.UPDATE,
            'PUT': API_PERMISSIONS.UPDATE,
            'PATCH': API_PERMISSIONS.UPDATE,
            'DELETE': API_PERMISSIONS.DELETE,
        },
        'list': {
            'POST': API_PERMISSIONS.CREATE,
        }
    }

    def is_valid_request(self, request):
        return True

    def get_model_permissions(self, request, permission_config):
        """
        Override this method to get specific model permissions for model permission config.
        """
        raise NotImplementedError  # pragma: no cover

    def get_required_permissions(self, method, is_detail=False):
        """
        Given a HTTP method, return the permission codename that the user is required to have.
        """

        perm = None

        if is_detail:
            if method in self.perms_map['detail']:
                perm = self.perms_map['detail'][method]
        elif method in self.perms_map['list']:
            perm = self.perms_map['list'][method]

        if not perm:
            perm = self.perms_map['default']

        return perm

    def has_permission(self, request, view):
        model_cls = getattr(view, 'model', None)
        queryset = getattr(view, 'queryset', None)

        if model_cls is None and queryset is not None:
            model_cls = queryset.model

        # Workaround to ensure DjangoModelPermissions are not applied
        # to the root view when using DefaultRouter.
        if model_cls is None:
            if getattr(view, '_ignore_model_permissions', False):
                return True

            raise RuntimeError('Cannot apply DjangoModelPermissions on a view that'
                               ' does not have `.model` or `.queryset` property.')

        # View in our case is a list view when action is either `create` or `list`. Otherwise it's a detail view.
        is_detail = getattr(view, 'action', None) not in ('create', 'list')
        perm = self.get_required_permissions(request.method, is_detail=is_detail)

        if self.is_valid_request(request):
            permission_config = getattr(model_cls, 'PERMISSION_CONFIG', None)
            if permission_config:
                model_permissions = self.get_model_permissions(request, permission_config)
                return perm in model_permissions
        return False

    def has_object_permission(self, request, view, obj):
        """
        Checks object permission. Only checked if general model permission check is satisfied.

        403 is raised by permission checker when this method returns False.
        """

        if not self.is_valid_request(request):
            return False

        model_cls = getattr(view, 'model', None)
        queryset = getattr(view, 'queryset', None)

        if model_cls is None and queryset is not None:
            model_cls = queryset.model

        perm = self.get_required_permissions(request.method, is_detail=True)
        permission_config = getattr(model_cls, 'PERMISSION_CONFIG', None)

        if not permission_config:
            return False

        model_permissions = self.get_model_permissions(request, permission_config)
        return perm in model_permissions


class Permission:
    def __init__(self, key, actions=None):
        self.key = key
        self.actions = set(actions) if actions else set()

    @classmethod
    def match(cls, permissions, action):
        for perm in permissions:
            if action in perm.actions:
                return perm

    def check_acl(self, request, acl):
        # Only apikey access
        if not request.auth:
            return False
        if request.auth.ignore_acl:
            return True

        perm_key = self.key

        # Check public acl
        if perm_key in acl.get('*', ()):
            return True
        # Users and groups ACL require a user
        if not request.auth_user:
            return False
        # Check users acl
        if 'users' in acl and perm_key in acl['users'].get(str(request.auth_user.id), ()):
            return True
        # Check groups acl
        if 'groups' in acl:
            groups_acl = acl['groups']
            for group_id in request.auth_user.get_group_ids():
                if perm_key in groups_acl.get(str(group_id), ()):
                    return True
        return False

    def __repr__(self):
        return 'Permission[key=%s, actions=(%s)]' % (self.key, ', '.join(self.actions))


class CheckAclPermissionBase(BasePermission):
    def has_parent_permission(self, request, view, permission=None):
        # Check parent objects permissions
        if hasattr(view, 'get_parents_query_dict'):
            from apps.core.abstract_models import AclAbstractModel
            read_permission = AclAbstractModel.READ_PERMISSION

            permission = permission or read_permission
            for obj in view.get_parents_query_dict().values():
                # Check permissions if object is an ACL model
                if isinstance(obj, AclAbstractModel) and request.auth and \
                        not permission.check_acl(request, obj.acl):
                    if permission.key == read_permission.key or not read_permission.check_acl(request, obj.acl):
                        raise ModelNotFound(obj.__class__)
                    return False
        return True

    def has_object_level_permission(self, request, view, obj):
        # Match object permissions
        perms = self.get_acl_model(view).get_acl_permissions()
        perm = Permission.match(perms, view.action)
        if perm:
            return perm.check_acl(request, obj.acl)
        return False

    def has_endpoint_level_permission(self, request, view):
        # Match endpoint permissions
        perms = self.get_acl_model(view).get_endpoint_acl_permissions()
        perm = Permission.match(perms, view.action)
        if perm:
            return perm.check_acl(request, view.get_endpoint_acl(request))
        return False

    def get_acl_model(self, view):
        return getattr(view, 'acl_model', view.model)


class CheckAclPermission(CheckAclPermissionBase):
    """
    Check ACL for current action on both object and endpoint level.
    """

    def has_object_permission(self, request, view, obj):
        return self.has_object_level_permission(request, view, obj)

    def has_permission(self, request, view):
        return self.has_parent_permission(request, view) and self.has_endpoint_level_permission(request, view)
