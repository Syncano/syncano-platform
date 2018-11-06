# coding=UTF8
from unittest import mock

from django.urls import reverse
from django_dynamic_fixture import G
from rest_framework import status
from rest_framework.test import APITestCase

from apps.core.exceptions import PermissionDenied
from apps.core.social_helpers import AdminSocialHelper
from apps.core.tests.mixins import CleanupTestCaseMixin
from apps.instances.helpers import set_current_instance
from apps.instances.models import Instance

from ..models import Admin, AdminSocialProfile

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


class SocialTestMockMixin:
    def setUp(self):
        super().setUp()
        self.response_mock = mock.Mock(status_code=200, json=mock.Mock(return_value=data_from_fb_with_email))
        self.get_mock = mock.Mock(return_value=self.response_mock)
        self.patcher = mock.patch('apps.core.social_helpers.requests.get', self.get_mock)
        self.patcher.start()

    def tearDown(self):
        super().tearDown()
        self.patcher.stop()


class SocialAuthViewTestSuite(SocialTestMockMixin):
    access_token = 'test_social_auth_access_token'
    post_data = {'access_token': access_token}

    def setUp(self):
        super().setUp()
        self.url = reverse('v1:authenticate_social', args=(self.backend,))

    def test_returns_200_when_user_found(self):
        response = self.client.post(self.url, self.post_data)
        self.assertEqual(response.status_code, 200)

    def test_returns_user_apikey_after_login(self):
        response = self.client.post(self.url, self.post_data)
        self.assertContains(response, 'account_key')

    def test_user_is_created(self):
        self.assertFalse(Admin.objects.exists())

        self.client.post(self.url, self.post_data)
        self.assertTrue(Admin.objects.exists())
        self.assertTrue(Admin.objects.first().is_active)

    def test_user_is_created_only_once(self):
        self.client.post(self.url, self.post_data)
        self.assertEquals(Admin.objects.count(), 1)

        self.client.post(self.url, {'access_token': 'another_token'})
        self.assertEquals(Admin.objects.count(), 1)

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
        self.response_mock.json.side_effect = [data_from_fb_with_email, data_from_github_emails,
                                               data_from_fb_with_email, data_from_github_emails]


class TestRegisterEmailIntegrityError(CleanupTestCaseMixin, SocialTestMockMixin, APITestCase):

    def setUp(self):
        super().setUp()
        self.assertFalse(Admin.objects.exists())
        self.social_register_url = reverse('v1:authenticate_social', args=('facebook',))
        self.client.post(self.social_register_url, {'access_token': 'facebook_token'})
        self.assertTrue(Admin.objects.exists())

    @mock.patch('apps.core.social_helpers.AdminSocialHelper.get_user')
    def test_register_email_integrity_error(self, get_user_mock):
        get_user_mock.side_effect = Admin.DoesNotExist
        response = self.client.post(self.social_register_url, {'access_token': 'facebook_token'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class TestSetPasswordView(CleanupTestCaseMixin, SocialTestMockMixin, APITestCase):
    def setUp(self):
        super().setUp()
        self.assertFalse(Admin.objects.exists())
        self.social_register_url = reverse('v1:authenticate_social', args=('facebook',))
        response = self.client.post(self.social_register_url, {'access_token': 'facebook_token'})
        self.assertTrue(Admin.objects.exists())

        account_key = response.data['account_key']
        self.admin_id = response.data['id']
        self.client.defaults['HTTP_X_API_KEY'] = account_key

        self.url = reverse('v1:admin_set_password')

    def test_social_user_can_set_password(self):
        response = self.client.post(self.url, {'password': 'testpassłord'})
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertTrue(Admin.objects.get(id=self.admin_id).has_usable_password())

    def test_user_cannot_set_empty_password(self):
        response = self.client.post(self.url, {'password': ''})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class TestSocialProfile(CleanupTestCaseMixin, APITestCase):
    user_class = Admin
    social_profile_class = AdminSocialProfile
    logger_class = AdminSocialHelper
    identifier = 'email'
    number_of_existing_users = 1

    def setUp(self):
        set_current_instance(G(Instance, name='testtest'))
        self.social_logger = self.logger_class()
        self.social_logger.backend = self.social_profile_class.BACKENDS.FACEBOOK

    def create_new(self, email):
        return self.user_class.objects.create(**{self.identifier: email})

    def test_if_creates_social_user(self):
        self.assertEqual(self.user_class.objects.count(), self.number_of_existing_users)
        self.social_logger.create_or_retrieve_social_user(
            social_id=SOCIAL_ID, email=EMAIL
        )
        self.assertEqual(self.social_profile_class.objects.count(), 1)
        self.assertEqual(self.user_class.objects.count(), self.number_of_existing_users + 1)

    def test_if_create_social_user_can_be_disallowed(self):
        self.assertEqual(self.user_class.objects.count(), self.number_of_existing_users)
        self.assertRaises(PermissionDenied, self.social_logger.create_or_retrieve_social_user,
                          social_id=SOCIAL_ID, email=EMAIL, allow_create=False)
        self.assertEqual(self.social_profile_class.objects.count(), 0)
        self.assertEqual(self.user_class.objects.count(), self.number_of_existing_users)

    def test_if_returns_admin_with_existing_email_but_creates_new_social_profile(self):
        self.create_new(EMAIL)
        self.assertEqual(self.social_profile_class.objects.count(), 0)
        self.social_logger.create_or_retrieve_social_user(
            social_id=SOCIAL_ID, email=EMAIL
        )
        self.assertEqual(self.user_class.objects.count(), self.number_of_existing_users + 1)
        self.assertEqual(self.social_profile_class.objects.count(), 1)

    def test_if_after_changing_email_in_social_account_admin_can_access_account(self):
        self.assertEqual(self.user_class.objects.count(), self.number_of_existing_users)
        admin = self.create_new(EMAIL)
        self.assertEqual(self.social_profile_class.objects.count(), 0)
        self.social_logger.create_or_retrieve_social_user(
            social_id=SOCIAL_ID, email=EMAIL
        )
        self.assertEqual(self.user_class.objects.count(), self.number_of_existing_users + 1)
        self.assertEqual(self.social_profile_class.objects.count(), 1)

        data_with_changed_email = data_from_fb_with_email.copy()
        data_with_changed_email['email'] = 'justyna.ilczuk@syncano.rocks'
        new_admin, was_created = self.social_logger.create_or_retrieve_social_user(
            social_id=SOCIAL_ID, email=EMAIL
        )
        self.assertFalse(was_created)
        self.assertEqual(self.user_class.objects.count(), self.number_of_existing_users + 1)
        self.assertEqual(self.social_profile_class.objects.count(), 1)

        self.assertEqual(admin.id, new_admin.id)

    def test_if_admin_can_access_the_same_account_from_different_social_profiles_linked_to_one_admin(self):
        admin = self.create_new(EMAIL)
        self.assertEqual(self.social_profile_class.objects.count(), 0)
        self.social_logger.create_or_retrieve_social_user(
            social_id=SOCIAL_ID, email=EMAIL
        )
        self.assertEqual(self.user_class.objects.count(), self.number_of_existing_users + 1)
        self.assertEqual(self.social_profile_class.objects.count(), 1)

        # let's assume now that now the same user logs in with google
        self.social_logger.backend = self.social_profile_class.BACKENDS.GOOGLE_OAUTH2

        new_admin, was_created = self.social_logger.create_or_retrieve_social_user(
            social_id=SOCIAL_ID, email=EMAIL
        )

        self.assertFalse(was_created)
        self.assertEqual(self.user_class.objects.count(), self.number_of_existing_users + 1)
        self.assertEqual(self.social_profile_class.objects.count(), 2)

        self.assertEqual(admin.id, new_admin.id)
