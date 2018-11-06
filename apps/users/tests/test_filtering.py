import json

from django.test import override_settings
from django.urls import reverse
from django_dynamic_fixture import G
from rest_framework import status

from apps.core.tests.testcases import SyncanoAPITestBase
from apps.data.models import DataObject, Klass
from apps.instances.helpers import set_current_instance
from apps.users.models import User


@override_settings(POST_TRANSACTION_SUCCESS_EAGER=True)
class UserFilteringTestBase(SyncanoAPITestBase):
    disable_user_profile = False
    url_name = 'v2:user-list'

    def setUp(self):
        super().setUp()
        self.url = reverse(self.url_name, args=(self.instance.name,))

        set_current_instance(self.instance)
        user_profile = Klass.get_user_profile()
        user_profile.schema = [{'name': 'int', 'type': 'integer', 'filter_index': True}]
        user_profile.save()

        # Add one random dataobject to make ids not in line with users
        G(DataObject)

        DataObject.load_klass(user_profile)
        self.user1 = User.objects.create(username='test@test.com', password='qweasd', profile_data={'int': 100})
        self.user2 = User.objects.create(username='test2@test.com', password='qweasd', profile_data={'int': 150})

    def assert_user_returned(self, query, user):
        response = self.client.get(self.url, {'query': json.dumps(query)})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['objects']), 1)
        self.assertEqual(response.data['objects'][0]['id'], user.id)

    def test_basic_filtering(self):
        query = {'username': {'_eq': 'test@test.com'}}
        self.assert_user_returned(query, self.user1)

        query = {'username': {'_startswith': 'test2'}}
        self.assert_user_returned(query, self.user2)

        query = {'id': {'_eq': self.user2.id}}
        self.assert_user_returned(query, self.user2)

        query = {'int': {'_lt': 120}}
        self.assert_user_returned(query, self.user1)

    def test_filtering_validation(self):
        for query in ({'username': {'_gt': None}},
                      {'int': {'_eq': 'argh'}}):
            response = self.client.get(self.url, {'query': json.dumps(query)})
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
