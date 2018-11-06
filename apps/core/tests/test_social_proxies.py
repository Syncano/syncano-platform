from unittest.mock import Mock, patch

from django.urls import reverse
from rest_framework import status
from rest_framework.response import Response
from rest_framework.test import APITestCase

from apps.users.tests.test_user_api import UserTestCase


class ProxyTestCase:

    def test_proxy_fails_without_code(self):
        response = self.client.get(self.url + self.without_code)
        self.assertEqual(response.status_code,
                         status.HTTP_400_BAD_REQUEST)

    def test_proxy_redirects_with_code(self):
        with patch(self.get_token,
                   Mock(return_value={'access_token': 'fake_token'})):

            response = self.client.get(self.url + self.with_code)
            self.assertEqual(response.status_code,
                             status.HTTP_302_FOUND)
            self.assertEqual(response.data['access_token'],
                             'fake_token')


class TestGithubSocialProxy(APITestCase, ProxyTestCase):
    url = reverse('v1:github_auth_proxy')
    with_code = '?code=xxx&redirect_uri=send_me_back'
    without_code = '?code='
    get_token = 'apps.core.social_proxies.GithubAuthProxyView._get_access_token'


class TestUserGithubSocialProxy(UserTestCase, APITestCase, ProxyTestCase):
    with_code = '?code=xxx&redirect_uri=send_me_back'
    without_code = '?code='
    get_token = 'apps.core.social_proxies.GithubAuthProxyView._get_access_token'

    def setUp(self):
        super().init_data()
        self.url = reverse('v1:user_github_auth_proxy', args=(self.instance.name,))


class TestUserLinkedinSocialProxy(UserTestCase, APITestCase, ProxyTestCase):
    with_code = '?code=xxx&redirect_uri=send_me_back'
    without_code = '?code='
    get_token = 'apps.core.social_proxies.LinkedinAuthProxyView._get_access_token'

    def setUp(self):
        super().init_data()
        self.url = reverse('v1:user_linkedin_auth_proxy', args=(self.instance.name,))


class TestUserTwitterSocialProxy(UserTestCase, APITestCase):

    without_verifier = '?oauth_token=xxx&oauth_token_secret=yyy'
    with_verifier = '?redirect_uri=send_me_back&oauth_token=xxx&oauth_verifier=yyy'

    def setUp(self):
        super().init_data()
        self.url = reverse('v1:user_twitter_auth_proxy', args=(self.instance.name,))

    @patch('apps.core.social_proxies.TwitterAuthProxyView.first_step_oauth1',
           return_value=Response())
    @patch('apps.core.social_proxies.TwitterAuthProxyView.second_step_oauth1',
           return_value=Response())
    def test_choosing_oauth_step(self, mock_step_2, mock_step_1):
        self.client.get(self.url + self.without_verifier)
        self.assertTrue(mock_step_1.called)
        self.assertFalse(mock_step_2.called)

        self.client.get(self.url + self.with_verifier)
        self.assertTrue(mock_step_2.called)

    def test_oauth_without_state(self):
        response = self.client.get(self.url + self.without_verifier)
        self.assertEqual(response.status_code,
                         status.HTTP_400_BAD_REQUEST)
