# coding=UTF8
import json

from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from apps.core.tests.mixins import CleanupTestCaseMixin


@override_settings(POST_TRANSACTION_SUCCESS_EAGER=True)
class AclTestCase(CleanupTestCaseMixin, APITestCase):
    default_count = 0

    def get_acl_url(self):
        raise NotImplementedError  # noqa

    def get_detail_url(self):
        raise NotImplementedError  # noqa

    def get_default_data(self):
        return {}

    def assert_object_access(self, acl=None, assert_denied=False, list_denied=False):
        self.set_object_acl(acl)

        detail_response = self.client.get(self.detail_url)
        list_response = self.client.get(self.list_url)

        if assert_denied:
            self.assertIn(detail_response.status_code, (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND))
        else:
            self.assertEqual(detail_response.status_code, status.HTTP_200_OK)

        if list_denied:
            self.assertIn(list_response.status_code, (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND))
        elif assert_denied:
            self.assertEqual(list_response.status_code, status.HTTP_200_OK)
            self.assertEqual(len(list_response.data['objects']), self.default_count)
        else:
            self.assertEqual(list_response.status_code, status.HTTP_200_OK)
            self.assertEqual(len(list_response.data['objects']), self.default_count + 1)

    def set_object_acl(self, acl=None):
        acl = acl or {}
        response = self.client.patch(self.detail_url, {'acl': json.dumps(acl)}, HTTP_X_API_KEY=self.instance.owner.key)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def assert_object_edit(self, acl=None, assert_denied=False):
        self.set_object_acl(acl)

        url = self.detail_url
        patch_response = self.client.patch(url)
        delete_response = self.client.delete(url)

        if assert_denied:
            self.assertIn(patch_response.status_code, (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND))
            self.assertIn(delete_response.status_code, (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND))
        else:
            self.assertEqual(patch_response.status_code, status.HTTP_200_OK)
            self.assertEqual(delete_response.status_code, status.HTTP_204_NO_CONTENT)

    def assert_endpoint_access(self, list_access=None, detail_access=None, endpoint_acl=None):
        if endpoint_acl is not None:
            response = self.client.put(self.get_acl_url(),
                                       {'acl': json.dumps(endpoint_acl)}, HTTP_X_API_KEY=self.instance.owner.key)
            self.assertEqual(response.status_code, status.HTTP_200_OK)

        list_access = list_access or {}
        detail_access = detail_access or {}

        for op, result in list_access.items():
            response = getattr(self.client, op)(self.list_url, self.get_default_data())
            if result:
                self.assertIn(response.status_code, (status.HTTP_200_OK, status.HTTP_201_CREATED),
                              '200/201 expected on "{}" on list, got {}'.format(op, response.status_code))
            else:
                self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN,
                                 '403 expected on "{}" on list, got {}'.format(op, response.status_code))

        for op, result in detail_access.items():
            response = getattr(self.client, op)(self.get_detail_url(), self.get_default_data())
            if result:
                self.assertIn(response.status_code, (status.HTTP_200_OK, status.HTTP_204_NO_CONTENT),
                              '200/204 expected on "{}" on detail, got {}'.format(op, response.status_code))
            else:
                self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN,
                                 '403 expected on "{}" on detail, got {}'.format(op, response.status_code))
