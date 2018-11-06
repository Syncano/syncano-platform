# coding=UTF8
from django.conf import settings
from rest_condition import And, Or
from rest_framework import generics, mixins, permissions, status, viewsets
from rest_framework.decorators import detail_route
from rest_framework.response import Response
from rest_framework.serializers import Serializer

from apps.admins.permissions import AdminHasPermissions
from apps.admins.serializers import SocialAuthSerializer
from apps.apikeys.permissions import ApiKeyHasPermissions, IsApiKeyAccess, IsApiKeyIgnoringAcl
from apps.billing.permissions import OwnerInGoodStanding
from apps.core.exceptions import UserNotFound, WrongPassword, WrongTokenCredentials
from apps.core.mixins.views import AtomicMixin, AutocompleteMixin, NestedViewSetMixin, SignalSenderModelMixin
from apps.core.social_helpers import UserSocialHelper
from apps.data.models import DataObject, Klass
from apps.data.v1.serializers import DataObjectSerializer
from apps.instances.mixins import InstanceBasedMixin
from apps.users.exceptions import UserGroupCountExceeded
from apps.users.models import Group, Membership, User
from apps.users.permissions import (
    HasCreateGroupPermission,
    HasCreateUserPermission,
    HasUser,
    IsMembershipForCurrentUser
)
from apps.users.signals import social_user_created
from apps.users.v1.serializers import (
    GroupMembershipSerializer,
    GroupSerializer,
    UserAuthSerializer,
    UserFullSerializer,
    UserMembershipSerializer
)


class SocialAuthView(AtomicMixin,
                     InstanceBasedMixin,
                     generics.GenericAPIView):
    serializer_class = SocialAuthSerializer
    response_serializer_class = UserFullSerializer
    # Profile serializer used for raw profile serialization (for triggers)
    data_serializer_class = DataObjectSerializer
    permission_classes = (
        Or(permissions.IsAuthenticated, IsApiKeyAccess),
        OwnerInGoodStanding,
    )

    def post(self, request, backend, *args, **kwargs):
        """Log user using social credentials.

        Available backends are now:
        `facebook`
        `google-oauth2`
        `github`
        `linkedin`
        `twitter`
        """
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            raise WrongTokenCredentials()

        # Use access token to get info about the user
        helper = UserSocialHelper()
        allow_create = request.auth.allow_user_create if request.auth is not None else True
        user, was_created = helper.register_by_access_token(serializer.data['access_token'], backend, allow_create)
        if user:
            if was_created:
                social_user_created.send(sender=User, view=self, instance=user)
            return Response(self.response_serializer_class(user, context=self.get_serializer_context()).data)
        raise WrongTokenCredentials()


class UserAuthView(InstanceBasedMixin,
                   generics.GenericAPIView):
    serializer_class = UserAuthSerializer
    response_serializer_class = UserFullSerializer

    permission_classes = (
        Or(permissions.IsAuthenticated, IsApiKeyAccess),
        OwnerInGoodStanding,
    )

    def post(self, request, *args, **kwargs):
        """
        Log user in if right email and password
        are provided.

        Returns data about user and `user_key`.
        """

        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            username = serializer.validated_data['username']
            password = serializer.validated_data['password']
            try:
                user = User.objects.get(username=username)

                if user.check_password(password):
                    return Response(self.response_serializer_class(user, context=self.get_serializer_context()).data)
                raise WrongPassword()
            except User.DoesNotExist:
                raise UserNotFound()

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class UserAccountView(AtomicMixin,
                      InstanceBasedMixin,
                      generics.RetrieveUpdateAPIView):
    serializer_class = UserFullSerializer
    permission_classes = (
        OwnerInGoodStanding,
        HasUser,
    )

    def get_object(self):
        return self.request.auth_user


class UserViewSet(AutocompleteMixin,
                  AtomicMixin,
                  InstanceBasedMixin,
                  SignalSenderModelMixin,
                  viewsets.ModelViewSet):
    model = User
    queryset = User.objects.prefetch_related('groups')
    serializer_class = UserFullSerializer
    user_serializer_class = UserFullSerializer
    data_serializer_class = DataObjectSerializer
    autocomplete_field = 'username'
    permission_classes = (
        Or(
            AdminHasPermissions,
            And(
                IsApiKeyAccess,
                Or(
                    IsApiKeyIgnoringAcl,
                    And(HasUser, ApiKeyHasPermissions),
                    HasCreateUserPermission
                )
            )
        ),
        OwnerInGoodStanding,
    )

    def initial(self, request, *args, **kwargs):
        initial = super().initial(request, *args, **kwargs)
        self.klass = Klass.get_user_profile()
        DataObject.load_klass(self.klass)
        return initial

    def get_queryset(self):
        base_query = super().get_queryset()

        if self.request.auth and self.request.auth_user:
            return base_query.filter(pk=self.request.auth_user.id)
        return base_query

    def get_object(self):
        obj = super().get_object()
        # get profile for deletions to work with triggers
        obj.profile = obj._profile_cache = DataObject.objects.filter(_klass=self.klass, owner=obj).get()
        return obj

    @detail_route(methods=['post'], serializer_class=Serializer)
    def reset_key(self, request, *args, **kwargs):
        user = self.get_object()
        user.reset()
        return Response(data=self.user_serializer_class(user,
                                                        context=self.get_serializer_context()).data)


class GroupViewSet(AutocompleteMixin,
                   AtomicMixin,
                   InstanceBasedMixin,
                   viewsets.ModelViewSet):
    model = Group
    queryset = Group.objects.all()
    serializer_class = GroupSerializer
    autocomplete_field = 'label'
    permission_classes = (
        Or(
            AdminHasPermissions,
            And(
                IsApiKeyAccess,
                Or(ApiKeyHasPermissions, HasCreateGroupPermission))
        ),
        OwnerInGoodStanding,
    )


class MembershipViewSet(AtomicMixin,
                        InstanceBasedMixin,
                        mixins.CreateModelMixin,
                        mixins.RetrieveModelMixin,
                        mixins.DestroyModelMixin,
                        mixins.ListModelMixin,
                        NestedViewSetMixin,
                        viewsets.GenericViewSet):
    model = Membership
    queryset = Membership.objects.all()
    serializer_class = UserMembershipSerializer

    def perform_create(self, serializer):
        # Lock on user for the duration of transaction to avoid race conditions
        user_id = serializer.validated_data['user'].id
        user = User.objects.select_for_update().get(pk=user_id)
        if Membership.objects.filter(user=user).count() >= settings.USER_GROUP_MAX_COUNT:
            raise UserGroupCountExceeded()
        serializer.save()


class UserMembershipViewSet(MembershipViewSet):
    serializer_class = UserMembershipSerializer
    permission_classes = (
        Or(AdminHasPermissions, And(ApiKeyHasPermissions, IsMembershipForCurrentUser)),
        OwnerInGoodStanding,
    )
    lookup_field = 'group_id'

    def get_queryset(self):
        return super().get_queryset().select_related('group')


class GroupMembershipViewSet(MembershipViewSet):
    serializer_class = GroupMembershipSerializer
    permission_classes = (
        Or(AdminHasPermissions, And(ApiKeyHasPermissions, HasUser)),
        OwnerInGoodStanding,
    )
    lookup_field = 'user_id'

    def get_queryset(self):
        base_query = super().get_queryset()

        if self.request.auth:
            return base_query.filter(user=self.request.auth_user.id)
        return base_query.select_related('user').prefetch_related('user__groups')
