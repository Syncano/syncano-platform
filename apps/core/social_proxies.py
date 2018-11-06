# coding=UTF8
import urllib.error
import urllib.parse
import urllib.request

import rapidjson as json
import requests
from django.conf import settings
from requests_oauthlib import OAuth1
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.serializers import Serializer
from rest_framework.views import APIView

from apps.core.exceptions import CodeMissing, StateMissing

from .helpers import cache


class OAuthProxyView(APIView):
    serializer_class = Serializer
    permission_classes = (permissions.AllowAny,)

    @staticmethod
    def _unpack_lists(x):
        return {k: v[0] for k, v in x.items()}

    def _parse_params(self, params):
        return self._unpack_lists(urllib.parse.parse_qs(params))

    def _parse_response(self, response):
        return response.json()

    def _get_access_token(self, code, redirect_uri):
        params = {
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'code': code,
            'grant_type': 'authorization_code',
            'redirect_uri': redirect_uri
        }
        response = requests.post(self.access_token_url, params=params)
        response.raise_for_status()

        return self._parse_response(response)

    def get(self, request, *args, **kwargs):
        query = request.META.get('QUERY_STRING', '')
        query_params = self._parse_params(query)

        code = query_params.pop('code', None)

        if code is None:
            raise CodeMissing()

        token_data = self._get_access_token(code, query_params['redirect_uri'])
        token_data.update(query_params)

        encoded_params = urllib.parse.urlencode(token_data)

        headers = {
            'Location': '{}#{}'.format(query_params['redirect_uri'], encoded_params),
        }
        return Response(
            headers=headers,
            data=token_data,
            status=status.HTTP_302_FOUND
        )


class LinkedinAuthProxyView(OAuthProxyView):
    """
    OAuth2 with explicit grant
    """
    access_token_url = 'https://www.linkedin.com/uas/oauth2/accessToken'
    client_id = settings.LINKEDIN_CLIENT_ID
    client_secret = settings.LINKEDIN_CLIENT_SECRET


class GithubAuthProxyView(OAuthProxyView):
    """
    OAuth2 with explicit grant
    """
    access_token_url = 'https://github.com/login/oauth/access_token'
    client_id = settings.GITHUB_CLIENT_ID
    client_secret = settings.GITHUB_CLIENT_SECRET

    def _parse_response(self, response):
        return self._unpack_lists(urllib.parse.parse_qs(response.text))


class TwitterAuthProxyView(OAuthProxyView):
    """
    OAuth1a
    """
    base_url = 'https://api.twitter.com/oauth/'

    request_token_url = base_url + 'request_token'
    access_token_url = base_url + 'access_token'
    authorize_url_tmpl = base_url + 'authenticate?&oauth_token={}'

    client_id = settings.TWITTER_CLIENT_ID
    client_secret = settings.TWITTER_CLIENT_SECRET

    TWITTER_CACHE_TEMPLATE = 'twitter_cache:{}'

    @staticmethod
    def _get_from_json(state, key):
        return json.loads(state)[key]

    @staticmethod
    def _dict_vals(dictionary, *args):
        return [dictionary.get(arg) for arg in args]

    def _get_request_token(self, oauth_proxy):
        params = {
            'client_key': self.client_id,
            'client_secret': self.client_secret,
        }
        r = requests.post(url=self.request_token_url,
                          params={'oauth_callback': oauth_proxy},
                          auth=OAuth1(**params))
        r.raise_for_status()
        return self._parse_params(r.text)

    def _get_access_token(self, resource_owner_key, resource_owner_secret, oauth_verifier):
        params = {
            'client_key': self.client_id,
            'client_secret': self.client_secret,
            'resource_owner_key': resource_owner_key,
            'resource_owner_secret': resource_owner_secret,
            'verifier': oauth_verifier
        }
        r = requests.post(url=self.access_token_url,
                          auth=OAuth1(**params))
        r.raise_for_status()
        return self._parse_params(r.text)

    def first_step_oauth1(self, query_params):

        # prevent spiders
        state = query_params.get('state')

        if state is None:
            raise StateMissing()

        credentials = self._get_request_token(
            self._get_from_json(state, 'oauth_proxy'))

        resource_owner_key, resource_owner_secret = self._dict_vals(credentials, 'oauth_token', 'oauth_token_secret')

        # we need to cache state to close the popup
        cache.set(self.TWITTER_CACHE_TEMPLATE.format(resource_owner_key),
                  {'secret': resource_owner_secret, 'state': query_params['state']},
                  timeout=300)

        credentials.update(query_params)
        authorize_url = self.authorize_url_tmpl.format(resource_owner_key)

        headers = {
            'Access-Control-Allow-Origin': '*',
            'Location': '{}#{}'.format(authorize_url,
                                       urllib.parse.urlencode(credentials)),
        }
        return Response(
            headers=headers,
            status=status.HTTP_302_FOUND
        )

    def second_step_oauth1(self, query_params):
        resource_owner_key, oauth_verifier = self._dict_vals(query_params, 'oauth_token', 'oauth_verifier')

        cached_step_one = cache.get(self.TWITTER_CACHE_TEMPLATE.format(resource_owner_key))
        resource_owner_secret, state = self._dict_vals(cached_step_one, 'secret', 'state')

        token_data = self._get_access_token(resource_owner_key,
                                            resource_owner_secret,
                                            oauth_verifier)
        token_data['access_token'] = '{oauth_token}:{oauth_token_secret}'.format(**token_data)

        token_data['state'] = state

        redirect_uri = self._get_from_json(token_data['state'], 'redirect_uri')

        headers = {
            'Access-Control-Allow-Origin': '*',
            'Location': '{}#{}'.format(redirect_uri,
                                       urllib.parse.urlencode(token_data))
        }
        return Response(
            headers=headers,
            data=token_data,
            status=status.HTTP_302_FOUND
        )

    def get(self, request, *args, **kwargs):
        query = request.META.get('QUERY_STRING', '')
        query_params = self._parse_params(query)

        if 'oauth_verifier' in query_params:
            return self.second_step_oauth1(query_params)
        return self.first_step_oauth1(query_params)
