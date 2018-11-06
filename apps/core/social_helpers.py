# coding=UTF8
import logging

import requests
from django.conf import settings
from requests_oauthlib import OAuth1

from apps.admins.models import Admin, AdminSocialProfile, SocialProfile
from apps.core.contextmanagers import revalidate_integrityerror
from apps.core.exceptions import InvalidSocialScopeMissingEmail, PermissionDenied, UnsupportedSocialBackend
from apps.users.models import User, UserSocialProfile

logger = logging.getLogger(__name__)


BACKEND_TO_ME_URL = {
    'facebook': 'https://graph.facebook.com/v2.4/me?fields=email',
    'google-oauth2': 'https://www.googleapis.com/oauth2/v1/userinfo',
    'github': 'https://api.github.com/user',
    'linkedin': 'https://api.linkedin.com/v1/people/~:(id,emailAddress)?format=json',
    'twitter': 'https://api.twitter.com/1.1/account/verify_credentials.json',
}


class SocialHelper:
    user_class = None
    disabled_backends = set([])

    def __init__(self):
        self.email = None
        self.backend = None
        self.social_id = None

    @staticmethod
    def _get_email(backend, raw_data, access_token):
        email = raw_data.get('email')

        if backend == 'github':
            response = requests.get('https://api.github.com/user/emails', params={'access_token': access_token})
            if response.status_code != 200:
                return None, False
            for data in response.json():
                if data['primary'] and data['verified']:
                    email = data['email']
        elif backend == 'linkedin':
            email = raw_data.get('emailAddress', '{id}@linkedin.com'.format(**raw_data))
        elif backend == 'twitter':
            email = '{id_str}@twitter.com'.format(**raw_data)

        return email

    def register_by_access_token(self, access_token, backend, allow_create=True):
        if backend not in BACKEND_TO_ME_URL:
            raise UnsupportedSocialBackend

        self.backend = SocialProfile.BACKENDS(backend).value

        if access_token is None:
            return None, False

        url = BACKEND_TO_ME_URL[backend]

        if backend in self.disabled_backends:
            return None, False

        if backend == 'linkedin':
            auth_header = 'Bearer {}'.format(access_token)
            response = requests.get(url, headers={'Authorization': auth_header})
        elif backend == 'twitter':
            if ':' not in access_token:
                return None, False

            access_token, access_token_secret = access_token.split(':', 1)
            oauth = OAuth1(settings.TWITTER_CLIENT_ID,
                           client_secret=settings.TWITTER_CLIENT_SECRET,
                           resource_owner_key=access_token,
                           resource_owner_secret=access_token_secret)
            response = requests.get(url, auth=oauth)
        else:
            response = requests.get(url, params={'access_token': access_token})

        if response.status_code != 200:
            return None, False

        raw_data = response.json()
        social_id = raw_data['id']
        email = self._get_email(backend, raw_data, access_token)

        return self.create_or_retrieve_social_user(social_id, email, allow_create)

    def create_or_retrieve_social_user(self, social_id, email, allow_create=True):
        """
        Get user object with social_id extracted from raw_data.
        Return also `was_created` flag to indicate if user was just created.

        :param raw_data:
        :return: user, was_created
        """
        self.social_id = social_id
        self.email = email

        try:
            return self.get_user(), False
        except self.user_class.DoesNotExist:
            if allow_create:
                return self.create_user(), True
            raise PermissionDenied('You do not have permission to create new user.')

    def get_user(self):
        return None

    def create_user(self):
        return None


class AdminSocialHelper(SocialHelper):
    user_class = Admin
    disabled_backends = {'linkedin', 'twitter'}

    def get_user(self):
        if not self.email:
            raise InvalidSocialScopeMissingEmail
        try:
            social_profile = AdminSocialProfile.objects.select_related('admin').get(
                social_id=self.social_id, backend=self.backend)
            return social_profile.admin
        except AdminSocialProfile.DoesNotExist:
            admin = Admin.objects.select_for_update().get(email=self.email)
            self._create_new_social_profile(self.social_id, self.backend, admin=admin)
            return admin

    def create_user(self):
        social_profile = self._create_new_social_profile(self.social_id, self.backend)
        return social_profile.admin

    def _create_new_social_profile(self, social_id, backend, admin=None):
        if admin is None:
            admin = self.user_class(email=self.email, is_active=True)
            with revalidate_integrityerror(self.user_class, admin.validate_unique):
                admin.save()

        social_profile = AdminSocialProfile(
            backend=backend,
            social_id=social_id,
            admin=admin,
        )
        with revalidate_integrityerror(AdminSocialProfile, social_profile.validate_unique):
            social_profile.save()

        return social_profile


class UserSocialHelper(SocialHelper):
    user_class = User

    def get_user(self):
        if not self.email:
            raise InvalidSocialScopeMissingEmail
        try:
            social_profile = UserSocialProfile.objects.select_related('user').get(
                social_id=self.social_id, backend=self.backend)
            return social_profile.user
        except UserSocialProfile.DoesNotExist:
            user = User.objects.select_for_update().get(username=self.email)
            self._create_new_social_profile(self.social_id, self.backend, user=user)
            return user

    def create_user(self):
        social_profile = self._create_new_social_profile(self.social_id, self.backend)
        return social_profile.user

    def _create_new_social_profile(self, social_id, backend, user=None):
        if user is None:
            user = self.user_class(username=self.email)
            with revalidate_integrityerror(self.user_class, user.validate_unique):
                user.save()

        social_profile = UserSocialProfile(
            backend=backend,
            social_id=social_id,
            user=user,
        )
        with revalidate_integrityerror(UserSocialProfile, user.validate_unique):
            social_profile.save()

        return social_profile
