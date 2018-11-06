# coding=UTF8
from django.conf import settings
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_condition import Or
from rest_framework import generics, mixins, permissions, status
from rest_framework.decorators import list_route
from rest_framework.response import Response
from rest_framework.serializers import Serializer
from rest_framework.viewsets import GenericViewSet

from apps.admins.exceptions import AdminAlreadyActivated, InvitationNotFound
from apps.admins.helpers import get_distinct_id
from apps.admins.models import Admin, AdminInstanceRole
from apps.admins.permissions import AdminHasPermissions, AllowSelfRoleDeletion, ProtectOwnerAccess
from apps.analytics.tasks import (
    NotifyAboutAdminActivation,
    NotifyAboutAdminPasswordReset,
    NotifyAboutAdminSignup,
    NotifyAboutLogIn,
    NotifyAboutLogInFailure
)
from apps.billing.permissions import OwnerInGoodStanding
from apps.core.exceptions import AdminNotFound, WrongPassword, WrongTokenCredentials
from apps.core.helpers import add_post_transaction_success_operation
from apps.core.mixins.views import AtomicMixin
from apps.core.social_helpers import AdminSocialHelper
from apps.core.tokens import default_token_generator
from apps.instances.mixins import InstanceBasedMixin
from apps.invitations.models import Invitation

from .serializers import (
    AdminActivationSerializer,
    AdminAuthSerializer,
    AdminChangePasswordSerializer,
    AdminEmailSerializer,
    AdminFullSerializer,
    AdminInstanceRoleSerializer,
    AdminInvitationSerializer,
    AdminRegisterSerializer,
    AdminResetPasswordConfirmationSerializer,
    AdminSetPasswordSerializer,
    InvitationKeySerializer,
    SocialAuthSerializer
)


class AuthView(AtomicMixin, generics.GenericAPIView):
    serializer_class = AdminAuthSerializer
    permission_classes = (permissions.AllowAny,)
    authentication_classes = []

    def post(self, request, *args, **kwargs):
        """Log Admin in if right email and password are provided.
        Returns data about user and `account_key`.
        """

        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            email = serializer.validated_data['email']
            password = serializer.validated_data['password']

            try:
                admin = Admin.objects.select_for_update().get(email=email)

                if admin.check_password(password):
                    admin_data = AdminFullSerializer(admin).data
                    admin_data['account_key'] = admin.key

                    admin.last_login = timezone.now()
                    admin.update_last_access(save=False)
                    admin.save(update_fields=('last_login', 'noticed_at', 'last_access'))
                    add_post_transaction_success_operation(NotifyAboutLogIn.delay, admin.id, email, 'password')
                    return Response(admin_data, status=status.HTTP_200_OK)

                NotifyAboutLogInFailure.delay(admin.id, email, 'password')
                raise WrongPassword()

            except Admin.DoesNotExist:
                raise AdminNotFound()

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class SocialAuthView(AtomicMixin, generics.GenericAPIView):
    serializer_class = SocialAuthSerializer
    permission_classes = (permissions.AllowAny,)
    authentication_classes = []

    def post(self, request, backend):
        """Log Admin using social credentials.

        Available backends are now:
        `facebook`
        `google-oauth2`
        `github`
        """
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            raise WrongTokenCredentials()

        # Use access token to get info about the user
        helper = AdminSocialHelper()
        admin, was_created = helper.register_by_access_token(serializer.data['access_token'], backend)

        if admin is None:
            raise WrongTokenCredentials()

        if was_created:
            context = self.get_task_context(admin, backend, request.data)
            add_post_transaction_success_operation(NotifyAboutAdminSignup.delay, admin.id, admin.email,
                                                   admin.created_at.strftime(settings.DATETIME_FORMAT), **context)

        admin_data = AdminFullSerializer(admin).data
        admin_data['account_key'] = admin.key
        admin_data['created'] = was_created

        admin.last_login = timezone.now()
        admin.update_last_access(save=False)
        admin.save(update_fields=('last_login', 'noticed_at', 'last_access'))
        add_post_transaction_success_operation(NotifyAboutLogIn.delay, admin.id, admin.email, backend)
        return Response(admin_data, status=status.HTTP_200_OK)

    def get_task_context(self, admin, backend, request_data):
        """
        In case we created admin, prepare context for sending sign-up event.
        """
        return {
            'backend': backend,
            'distinct_id': get_distinct_id(request_data)
        }


class RegisterView(AtomicMixin,
                   generics.GenericAPIView):
    serializer_class = AdminRegisterSerializer
    permission_classes = (permissions.AllowAny,)
    token_generator = default_token_generator

    def post(self, request, *args, **kwargs):
        """Create admin.

        Requires:
        email,
        password,
        invitation_key - optional invitation key
        """

        serializer = self.get_serializer(data=request.data)

        if serializer.is_valid():
            admin = serializer.save()
            admin_data = AdminFullSerializer(admin).data
            admin_data['account_key'] = admin.key

            context = self.get_task_context(admin, request.data)
            add_post_transaction_success_operation(NotifyAboutAdminSignup.delay, admin.id, admin.email,
                                                   admin.created_at.strftime(settings.DATETIME_FORMAT), **context)
            return Response(admin_data, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def get_task_context(self, admin, request_data):
        token = self.token_generator.make_token(admin)
        uid = urlsafe_base64_encode(force_bytes(admin.pk)).decode()
        activation_url = settings.GUI_ACTIVATION_URL % {'uid': uid, 'token': token}
        return {
            'activation_url': activation_url,
            'distinct_id': get_distinct_id(request_data)
        }


class ResendActivationEmailView(AtomicMixin,
                                generics.GenericAPIView):
    serializer_class = AdminEmailSerializer
    permission_classes = (permissions.AllowAny,)
    token_generator = default_token_generator

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)

        if serializer.is_valid():
            admin = serializer.admin

            if admin.is_active:
                raise AdminAlreadyActivated()

            admin.send_activation_email(default_token_generator)
            return Response(status=status.HTTP_204_NO_CONTENT)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class AccountView(AtomicMixin, generics.RetrieveUpdateAPIView):
    """See or update your account data.

    Admin has to provide api_key to be authenticated
    via http header or query param.
    """

    serializer_class = AdminFullSerializer
    permission_classes = (
        permissions.IsAuthenticated,
    )
    token_generator = default_token_generator

    def get_object(self):
        return self.request.user

    def perform_update(self, serializer):
        admin = serializer.instance
        Admin.objects.select_for_update().get(pk=admin.pk)
        validated_data = serializer.validated_data

        if 'email' in validated_data and validated_data['email'] != admin.email:
            admin.is_active = False
            admin.send_activation_email(self.token_generator)
        return super().perform_update(serializer)


class AdminResetKey(AtomicMixin, generics.GenericAPIView):
    """Reset admin account key"""

    serializer_class = Serializer
    permission_classes = (
        permissions.IsAuthenticated,
    )

    def post(self, request, *args, **kwargs):
        admin = self.request.user

        admin_data = AdminFullSerializer(admin).data
        admin.reset()
        admin_data['account_key'] = admin.key
        return Response(admin_data, status=status.HTTP_200_OK)


class AdminChangePasswordView(AtomicMixin, generics.GenericAPIView):
    """Change admin password"""

    serializer_class = AdminChangePasswordSerializer
    permission_classes = (
        permissions.IsAuthenticated,
    )

    def get_object(self):
        return self.request.user

    def post(self, request, *args, **kwargs):
        admin = self.get_object()
        serializer = self.get_serializer(data=request.data)

        if serializer.is_valid():
            admin.set_password(serializer.data['new_password'])
            admin.save()
            return Response(status=status.HTTP_204_NO_CONTENT)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class AdminResetPasswordView(generics.GenericAPIView):
    """Reset admin password"""

    serializer_class = AdminEmailSerializer
    permission_classes = (
        permissions.AllowAny,
    )
    token_generator = default_token_generator

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)

        if serializer.is_valid():
            context = self.get_task_context(serializer.admin)
            NotifyAboutAdminPasswordReset.delay(**context)
            return Response(status=status.HTTP_204_NO_CONTENT)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def get_task_context(self, admin):
        token = self.token_generator.make_token(admin)
        uid = urlsafe_base64_encode(force_bytes(admin.pk)).decode()
        return {
            'admin_id': admin.id,
            'uid': uid,
            'token': token,
        }


class AdminResetPasswordConfirmationView(AtomicMixin, generics.GenericAPIView):
    serializer_class = AdminResetPasswordConfirmationSerializer
    permission_classes = (
        permissions.AllowAny,
    )
    token_generator = default_token_generator

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)

        if serializer.is_valid():
            admin = serializer.admin
            admin.set_password(serializer.data['new_password'])
            admin.save()
            admin_data = AdminFullSerializer(admin).data
            admin_data['account_key'] = admin.key
            return Response(admin_data, status=status.HTTP_200_OK)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class AdminSetPasswordView(AtomicMixin, generics.GenericAPIView):
    serializer_class = AdminSetPasswordSerializer
    permission_classes = (
        permissions.IsAuthenticated,
    )

    def get_object(self):
        return self.request.user

    def post(self, request, *args, **kwargs):
        admin = self.get_object()
        serializer = self.get_serializer(data=request.data)

        if serializer.is_valid():
            if admin.has_usable_password():
                errors = {'password': ["Admin already has password."]}
                return Response(errors, status=status.HTTP_400_BAD_REQUEST)
            admin.set_password(serializer.data['password'])
            admin.save()
            return Response(status=status.HTTP_204_NO_CONTENT)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class AdminViewSet(AtomicMixin,
                   InstanceBasedMixin,
                   mixins.RetrieveModelMixin,
                   mixins.UpdateModelMixin,
                   mixins.DestroyModelMixin,
                   mixins.ListModelMixin,
                   GenericViewSet):
    """API endpoint for admins added to given instance"""

    model = AdminInstanceRole
    queryset = AdminInstanceRole.objects
    lookup_field = 'admin_id'
    serializer_class = AdminInstanceRoleSerializer
    permission_classes = (Or(AdminHasPermissions, AllowSelfRoleDeletion), ProtectOwnerAccess, OwnerInGoodStanding)

    def get_queryset(self):
        qs = super().get_queryset()
        return qs.select_related('role', 'admin').filter(instance=self.request.instance)


class AdminActivationView(AtomicMixin,
                          generics.GenericAPIView):
    """API to activate admin by email"""

    serializer_class = AdminActivationSerializer
    permission_classes = (permissions.AllowAny,)
    token_generator = default_token_generator

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)

        if serializer.is_valid():
            admin = serializer.admin
            admin.is_active = True
            admin.last_login = timezone.now()
            admin.save(update_fields=('last_login', 'is_active',))

            add_post_transaction_success_operation(
                NotifyAboutAdminActivation.delay,
                admin_id=admin.id, email=admin.email, **serializer.data
            )

            admin_data = AdminFullSerializer(admin).data
            admin_data['account_key'] = admin.key
            return Response(admin_data, status=status.HTTP_200_OK)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class AdminInvitationViewSet(AtomicMixin,
                             mixins.RetrieveModelMixin,
                             mixins.DestroyModelMixin,
                             mixins.ListModelMixin,
                             GenericViewSet):
    """API endpoint for admin invitations"""

    model = Invitation
    queryset = Invitation.objects.all()
    serializer_class = AdminInvitationSerializer
    permission_classes = (
        permissions.IsAuthenticated,
    )

    def get_queryset(self):
        qs = super().get_queryset()
        return qs.filter(
            admin=self.request.user,
            state=Invitation.STATE_CHOICES.NEW
        ).select_related('inviter', 'instance', 'role')

    def destroy(self, request, *args, **kwargs):
        obj = self.get_object()
        obj.state = Invitation.STATE_CHOICES.DECLINED
        obj.save(update_fields=('state', 'updated_at',))
        return Response(status=status.HTTP_204_NO_CONTENT)

    @list_route(serializer_class=InvitationKeySerializer, methods=['post'])
    def accept(self, request):
        serializer = self.get_serializer(data=request.data)

        if serializer.is_valid():
            invitation_key = serializer.validated_data['invitation_key']
            try:
                invitation = Invitation.objects.select_for_update(of=('self',)).select_related('role').get(
                    state=Invitation.STATE_CHOICES.NEW,
                    key=invitation_key)
            except Invitation.DoesNotExist:
                raise InvitationNotFound()
            invitation.accept(request.user)

            return Response(status=status.HTTP_204_NO_CONTENT)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
