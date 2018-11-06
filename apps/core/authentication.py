# coding=UTF8
import re

from rest_framework import authentication, exceptions

from apps.admins.models import Admin, AnonymousAdmin
from apps.apikeys.models import ApiKey
from apps.core.helpers import Cached, check_parity, verify_token
from apps.instances.helpers import get_current_instance
from apps.users.models import User

AUTHORIZATION_HEADER = 'HTTP_AUTHORIZATION'
API_KEY_REGEX = re.compile(r'[a-f0-9]{40}\Z', re.IGNORECASE)


class ApiKeyAuthentication(authentication.BaseAuthentication):

    @classmethod
    def get_api_key(cls, request):
        api_key = request.META.get('HTTP_X_API_KEY') or request.GET.get('api_key') or request.GET.get('apikey')
        if api_key:
            return api_key

        authorization_header = request.META.get(AUTHORIZATION_HEADER)
        if authorization_header:
            try:
                _, api_key = authorization_header.split(' ', 2)
                return api_key
            except ValueError:
                pass

        # Check if it is in POST (to avoid preflight)
        if isinstance(request.data, dict):
            return request.data.get('_api_key')

    @classmethod
    def get_user_key(cls, request):
        user_key = request.META.get('HTTP_X_USER_KEY') or request.GET.get('user_key') or request.GET.get('userkey')
        # Check if it is in POST (to avoid preflight)
        if not user_key and isinstance(request.data, dict):
            return request.data.get('_user_key')
        return user_key

    @classmethod
    def get_staff_key(cls, request):
        return request.META.get('HTTP_X_STAFF_KEY') or request.GET.get('staff_key', request.GET.get('staffkey'))

    @classmethod
    def get_admin_by_key(cls, api_key):
        try:
            return Cached(Admin, kwargs={'key': api_key}).get()
        except Admin.DoesNotExist:
            raise exceptions.AuthenticationFailed('No such API Key.')

    @classmethod
    def get_admin_from_token(cls, token, instance):
        if not instance:
            return

        instance_pk = verify_token(token)
        if instance_pk != instance.pk:
            return

        try:
            return Cached(Admin, kwargs={'id': instance.owner_id}).get()
        except ApiKey.DoesNotExist:
            raise exceptions.AuthenticationFailed('Invalid token.')

    @classmethod
    def get_auth(cls, api_key, instance):
        lookup_kwargs = {'key': api_key}
        if instance:
            lookup_kwargs['instance'] = instance

        try:
            return Cached(ApiKey, kwargs=lookup_kwargs).get()
        except ApiKey.DoesNotExist:
            raise exceptions.AuthenticationFailed('No such API Key.')

    @classmethod
    def get_auth_user(cls, request):
        user_key = cls.get_user_key(request)

        if user_key:
            try:
                return Cached(User, kwargs=dict(key=user_key)).get()
            except User.DoesNotExist:
                pass

    def authenticate(self, request):
        api_key = self.get_api_key(request)
        admin = getattr(request._request, 'user', AnonymousAdmin())
        auth = getattr(request._request, 'auth', None)
        auth_user = getattr(request._request, 'auth_user', None)
        staff_user = getattr(request._request, 'staff_user', None)
        instance = getattr(request._request, 'instance', None)

        # Initialize default auth_user first so that permission classes are sane
        request.auth_user = None
        request._request.auth_user = None

        if api_key:
            if not API_KEY_REGEX.match(api_key):
                # Verify if we're dealing with a token
                admin = self.get_admin_from_token(api_key, instance)
                if not admin:
                    raise exceptions.AuthenticationFailed('No such API Key.')
            else:
                if check_parity(api_key):
                    admin = self.get_admin_by_key(api_key)
                else:
                    auth = self.get_auth(api_key, instance)
                    if auth and get_current_instance():
                        auth_user = self.get_auth_user(request)

            staff_key = self.get_staff_key(request)
            if staff_key and API_KEY_REGEX.match(staff_key) and check_parity(staff_key):
                staff_user = self.get_admin_by_key(staff_key)
                staff_user = staff_user if staff_user.is_staff else None

        # Save auth user manually
        request.auth_user = auth_user
        request.staff_user = staff_user

        # Save user inside wrapped request so that middlewares also see it
        request._request.user = admin
        request._request.auth = auth
        request._request.auth_user = auth_user
        request._request.staff_user = staff_user
        return admin, auth
