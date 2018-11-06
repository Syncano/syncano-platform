# coding=UTF8
from django.db import transaction
from django.urls import reverse
from django_dynamic_fixture import G
from rest_framework.test import APITestCase

from apps.admins.tests.test_social_login import SocialTestMockMixin
from apps.apikeys.models import ApiKey
from apps.core.social_helpers import UserSocialHelper
from apps.core.tests.mixins import CleanupTestCaseMixin
from apps.instances.helpers import get_instance_db, set_current_instance
from apps.instances.models import Instance
from apps.users.models import User, UserSocialProfile

SOCIAL_ID = '385738748243423'
EMAIL = 'justyna.ilczuk@syncano.com'

data_from_fb_with_email = {
    'verified': True,
    'id': SOCIAL_ID,
    'email': EMAIL,
    # ...
}

data_from_github_emails = [
    {
        'verified': True,
        'primary': True,
        'email': EMAIL,
        # ...
    }
]

data_from_linkedin_without_email = {
    'verified': True,
    'id': SOCIAL_ID,
    # ...
}

data_from_linkedin_with_email = {
    'verified': True,
    'id': SOCIAL_ID,
    'emailAddress': EMAIL,
    # ...
}

data_from_twitter = {
    'verified': True,
    'id': int(SOCIAL_ID),
    'id_str': SOCIAL_ID,
    'name': 'Ambroży Kleks',
    # ...
}


class SocialAuthViewTestSuite(SocialTestMockMixin):
    post_data = {'access_token': 'test_social_auth_access_token'}

    def setUp(self):
        super().setUp()
        self.instance = G(Instance, name='testinstance')
        self.apikey = G(ApiKey, allow_user_create=True, instance=self.instance)
        self.client.defaults['HTTP_X_API_KEY'] = self.apikey.key
        self.url = reverse('v1:authenticate_social_user', args=(self.instance.name, self.backend,))

    def test_returns_200_when_user_found(self):
        response = self.client.post(self.url, self.post_data)
        self.assertEqual(response.status_code, 200)

    def test_returns_user_apikey_after_login(self):
        response = self.client.post(self.url, self.post_data)
        self.assertContains(response, 'user_key')

    def test_user_is_created(self):
        set_current_instance(self.instance)
        self.assertFalse(User.objects.exists())

        self.client.post(self.url, self.post_data)
        set_current_instance(self.instance)
        self.assertTrue(User.objects.exists())

    def test_user_is_created_only_once(self):
        self.client.post(self.url, self.post_data)
        set_current_instance(self.instance)
        self.assertEquals(User.objects.count(), 1)

        self.client.post(self.url, self.post_data)
        self.assertEquals(User.objects.count(), 1)

    def test_user_authenticates_with_empty_access_token(self):
        self.response_mock.status_code = 403
        response = self.client.post(self.url)
        self.assertEquals(response.status_code, 401)

    def test_user_authenticates_wrong_access_token(self):
        self.response_mock.status_code = 403
        response = self.client.post(self.url, {'access_token': 'imjustwrong'})
        self.assertEquals(response.status_code, 401)


class TestFacebookAuthView(SocialAuthViewTestSuite,
                           CleanupTestCaseMixin,
                           APITestCase):
    backend = "facebook"


class TestGoogleAuthView(SocialAuthViewTestSuite,
                         CleanupTestCaseMixin,
                         APITestCase):
    backend = "google-oauth2"


class TestGithubAuthView(SocialAuthViewTestSuite,
                         CleanupTestCaseMixin,
                         APITestCase):
    backend = "github"

    def setUp(self):
        super().setUp()
        self.response_mock.json.side_effect = [data_from_fb_with_email,
                                               data_from_github_emails,
                                               data_from_fb_with_email,
                                               data_from_github_emails]


class TestLinkedinAuthView(SocialAuthViewTestSuite,
                           CleanupTestCaseMixin,
                           APITestCase):
    backend = "linkedin"

    def setUp(self):
        super().setUp()
        self.response_mock.json.side_effect = [data_from_linkedin_with_email,
                                               data_from_linkedin_with_email,
                                               data_from_fb_with_email,
                                               data_from_fb_with_email,
                                               data_from_linkedin_without_email,
                                               data_from_linkedin_without_email]


class TestTwitterAuthView(SocialAuthViewTestSuite,
                          CleanupTestCaseMixin,
                          APITestCase):
    backend = "twitter"
    post_data = {'access_token': 'test_access_token:test_token_secret'}

    def setUp(self):
        super().setUp()
        self.response_mock.json.side_effect = [data_from_twitter,
                                               data_from_twitter,
                                               data_from_fb_with_email,
                                               data_from_fb_with_email]


class TestSocialProfile(CleanupTestCaseMixin, APITestCase):
    user_class = User
    social_profile_class = UserSocialProfile
    logger_class = UserSocialHelper
    identifier = 'username'
    number_of_existing_users = 0

    def setUp(self):
        self.instance = G(Instance, name='testtest')
        set_current_instance(self.instance)
        self.db = get_instance_db(self.instance)
        self.social_logger = self.logger_class()
        self.social_logger.backend = self.social_profile_class.BACKENDS.FACEBOOK

    def create_new(self, email):
        return self.user_class.objects.create(**{self.identifier: email})

    def test_if_creates_social_user(self):
        self.assertEqual(self.user_class.objects.count(), self.number_of_existing_users)
        with transaction.atomic(self.db):
            self.social_logger.create_or_retrieve_social_user(
                social_id=SOCIAL_ID, email=EMAIL
            )
        self.assertEqual(self.social_profile_class.objects.count(), 1)
        self.assertEqual(self.user_class.objects.count(), self.number_of_existing_users + 1)

    def test_if_returns_user_with_existing_email_but_creates_new_social_profile(self):
        self.create_new(EMAIL)
        self.assertEqual(self.social_profile_class.objects.count(), 0)
        with transaction.atomic(self.db):
            self.social_logger.create_or_retrieve_social_user(
                social_id=SOCIAL_ID, email=EMAIL
            )
        self.assertEqual(self.user_class.objects.count(), self.number_of_existing_users + 1)
        self.assertEqual(self.social_profile_class.objects.count(), 1)

    def test_if_after_changing_email_in_social_account_user_can_access_account(self):
        self.assertEqual(self.user_class.objects.count(), self.number_of_existing_users)
        user = self.create_new(EMAIL)
        self.assertEqual(self.social_profile_class.objects.count(), 0)
        with transaction.atomic(self.db):
            self.social_logger.create_or_retrieve_social_user(
                social_id=SOCIAL_ID, email=EMAIL
            )
        self.assertEqual(self.user_class.objects.count(), self.number_of_existing_users + 1)
        self.assertEqual(self.social_profile_class.objects.count(), 1)

        data_with_changed_email = data_from_fb_with_email.copy()
        data_with_changed_email['email'] = 'justyna.ilczuk@syncano.rocks'
        with transaction.atomic(self.db):
            new_user, was_created = self.social_logger.create_or_retrieve_social_user(
                social_id=SOCIAL_ID, email=EMAIL
            )
        self.assertFalse(was_created)
        self.assertEqual(self.user_class.objects.count(), self.number_of_existing_users + 1)
        self.assertEqual(self.social_profile_class.objects.count(), 1)

        self.assertEqual(user.id, new_user.id)

    def test_if_user_can_access_the_same_account_from_different_social_profiles_linked_to_one_user(self):
        user = self.create_new(EMAIL)
        self.assertEqual(self.social_profile_class.objects.count(), 0)
        with transaction.atomic(self.db):
            self.social_logger.create_or_retrieve_social_user(
                social_id=SOCIAL_ID, email=EMAIL
            )
        self.assertEqual(self.user_class.objects.count(), self.number_of_existing_users + 1)
        self.assertEqual(self.social_profile_class.objects.count(), 1)

        # let's assume now that now the same user logs in with google
        self.social_logger.backend = self.social_profile_class.BACKENDS.GOOGLE_OAUTH2

        with transaction.atomic(self.db):
            new_user, was_created = self.social_logger.create_or_retrieve_social_user(
                social_id=SOCIAL_ID, email=EMAIL
            )

        self.assertFalse(was_created)
        self.assertEqual(self.user_class.objects.count(), self.number_of_existing_users + 1)
        self.assertEqual(self.social_profile_class.objects.count(), 2)

        self.assertEqual(user.id, new_user.id)
