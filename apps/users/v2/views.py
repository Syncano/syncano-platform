# coding=UTF8
from rest_condition import Or
from rest_framework import status
from rest_framework.decorators import detail_route, list_route
from rest_framework.response import Response
from rest_framework.serializers import Serializer

from apps.admins.permissions import AdminHasPermissions
from apps.billing.permissions import OwnerInGoodStanding
from apps.core.mixins.views import EndpointAclMixin
from apps.core.permissions import CheckAclPermission
from apps.data.models import DataObject, Klass
from apps.data.v2.serializers import DataObjectSerializer
from apps.data.v2.views import ObjectViewSet
from apps.users.mixins import UserProfileViewMixin
from apps.users.models import User
from apps.users.permissions import CheckGroupMembershipAclPermission
from apps.users.v1 import views as v1_views
from apps.users.v2.serializers import (
    GroupMembershipSerializer,
    GroupSerializer,
    UserDetailSerializer,
    UserFullDetailSerializer,
    UserFullSerializer,
    UserMembershipSerializer,
    UserObjectSerializer,
    UserSchemaSerializer,
    UserSerializer
)


class GroupViewSet(EndpointAclMixin, v1_views.GroupViewSet):
    serializer_class = GroupSerializer
    permission_classes = (
        Or(
            # Check admin permissions
            AdminHasPermissions,
            # Check API Key ACL
            CheckAclPermission,
        ),
        OwnerInGoodStanding,
    )

    endpoint_acl_object_field = 'groups_acl'

    def get_queryset(self):
        base_query = super().get_queryset()
        return base_query.filter_acl(self.request)


class SocialAuthView(UserProfileViewMixin, v1_views.SocialAuthView):
    response_serializer_class = UserObjectSerializer
    # Profile serializer used for raw profile serialization (for triggers)
    data_serializer_class = DataObjectSerializer


class UserAuthView(UserProfileViewMixin, v1_views.UserAuthView):
    response_serializer_class = UserObjectSerializer


class UserAccountView(UserProfileViewMixin, v1_views.UserAccountView):
    serializer_class = UserObjectSerializer


class UserViewSet(UserProfileViewMixin, ObjectViewSet):
    acl_model = User
    lookup_field = 'owner_id'

    serializer_class = UserSerializer
    serializer_detail_class = UserDetailSerializer
    full_serializer_class = UserFullSerializer
    full_serializer_detail_class = UserFullDetailSerializer
    # Profile serializer used for raw profile serialization (for triggers)
    data_serializer_class = DataObjectSerializer

    query_fields = {'id', 'username', 'created_at', 'updated_at', 'revision', 'channel', 'channel_room'}
    query_fields_extra = {
        'id': {'lookup': 'owner_id', 'type': int},
        'username': {'lookup': 'owner__username'},
        'channel': {'lookup': 'channel__name', 'type': str},
    }

    def get_queryset(self):
        base_query = super().get_queryset().filter(_klass=self.klass)
        return base_query.select_related('owner').prefetch_related('owner__groups')

    @classmethod
    def get_lookup(self, value):
        return DataObject.objects.get(_klass=Klass.get_user_profile(), owner=value)

    def get_serializer_class(self):
        if getattr(self, 'action', None) in ('create', 'retrieve', 'list', 'update', 'partial_update', 'destroy'):
            # For standard actions, use full serializer if applicable
            if self.request.user.is_authenticated:
                if self._is_request_to_detail_endpoint():
                    return self.full_serializer_detail_class
                return self.full_serializer_class
        return super().get_serializer_class()

    def perform_destroy(self, instance):
        super().perform_destroy(instance)
        instance.owner.delete()

    @detail_route(methods=['post'], serializer_detail_class=Serializer)
    def reset_key(self, request, *args, **kwargs):
        obj = self.get_object()
        obj.owner.reset()
        return Response(data=self.full_serializer_class(obj, context=self.get_serializer_context()).data)

    @list_route(serializer_class=UserSchemaSerializer,
                methods=['get', 'put', 'patch'],
                permission_classes=(OwnerInGoodStanding, AdminHasPermissions))
    def schema(self, request, **kwargs):
        obj = self.klass

        if request.method == 'GET':
            serializer = self.get_serializer(obj)
            return Response(serializer.data)

        serializer = self.get_serializer(obj, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class UserMembershipViewSet(v1_views.UserMembershipViewSet):
    """
    Users in a Group ViewSet
    """

    serializer_class = UserMembershipSerializer

    @property
    def user(self):
        if hasattr(self, 'dataobject'):
            return User(id=self.dataobject.owner_id)
        return None

    def get_parents_query_dict(self):
        parents_query_dict = super().get_parents_query_dict()
        parents_query_dict['user'] = parents_query_dict['user'].owner_id
        return parents_query_dict


class GroupMembershipViewSet(v1_views.GroupMembershipViewSet):
    """
    Groups of a User ViewSet
    """

    serializer_class = GroupMembershipSerializer
    permission_classes = (
        Or(
            # Check admin permissions
            AdminHasPermissions,
            # Check API Key ACL
            CheckGroupMembershipAclPermission,
        ),
        OwnerInGoodStanding,
    )

    def get_queryset(self):
        base_query = super(v1_views.GroupMembershipViewSet, self).get_queryset()
        return base_query.select_related('user').prefetch_related('user__groups')
