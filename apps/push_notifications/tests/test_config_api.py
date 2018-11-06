from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django_dynamic_fixture import G
from rest_framework import status

from apps.core.tests.testcases import SyncanoAPITestBase
from apps.instances.helpers import set_current_instance
from apps.push_notifications.models import APNSConfig, GCMConfig


class TestGCMConfigAPI(SyncanoAPITestBase):

    def setUp(self):
        super().setUp()
        set_current_instance(self.instance)
        self.config = G(GCMConfig)
        self.url = reverse('v1:gcm-config', args=(self.instance.name, ))

    def test_if_can_retrieve_config(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['production_api_key'], self.config.production_api_key)
        self.assertEqual(response.data['development_api_key'], self.config.development_api_key)

    def test_if_can_delete_config(self):
        response = self.client.delete(self.url)
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_if_can_partial_update_config(self):
        data = {'production_api_key': 'production_api_key_123'}
        response = self.client.patch(self.url, data)
        config = GCMConfig.objects.get(pk=self.config.pk)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(config.production_api_key, data['production_api_key'])
        self.assertEqual(config.development_api_key, self.config.development_api_key)

    def test_if_can_update_config(self):
        data = {
            'production_api_key': 'production_api_key_123',
            'development_api_key': 'development_api_key_123',
        }
        response = self.client.put(self.url, data)
        config = GCMConfig.objects.get(pk=self.config.pk)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(config.production_api_key, data['production_api_key'])
        self.assertEqual(config.development_api_key, data['development_api_key'])


class TestAPNSConfigAPI(SyncanoAPITestBase):

    def setUp(self):
        super().setUp()
        set_current_instance(self.instance)
        self.config = G(APNSConfig)
        self.url = reverse('v1:apns-config', args=(self.instance.name, ))

    def test_if_can_retrieve_config(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['production_certificate_name'], self.config.production_certificate_name)
        self.assertEqual(response.data['production_bundle_identifier'], self.config.production_bundle_identifier)
        self.assertEqual(response.data['development_certificate_name'], self.config.development_certificate_name)
        self.assertEqual(response.data['development_bundle_identifier'], self.config.development_bundle_identifier)

    def test_if_can_delete_config(self):
        response = self.client.delete(self.url)
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_if_can_partial_update_config(self):
        data = {'production_certificate_name': 'production_certificate_name_123'}
        response = self.client.patch(self.url, data)
        config = APNSConfig.objects.get(pk=self.config.pk)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(config.production_certificate_name, data['production_certificate_name'])
        self.assertEqual(config.development_certificate_name, self.config.development_certificate_name)

    def test_if_can_update_config(self):
        data = {
            'production_certificate_name': 'production_certificate_name_123',
            'production_bundle_identifier': 'production_bundle_identifier_123',
            'development_certificate_name': 'development_certificate_name_123',
            'development_bundle_identifier': 'development_bundle_identifier_123',
        }
        response = self.client.put(self.url, data)
        config = APNSConfig.objects.get(pk=self.config.pk)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(config.production_certificate_name, data['production_certificate_name'])
        self.assertEqual(config.production_bundle_identifier, data['production_bundle_identifier'])
        self.assertEqual(config.development_certificate_name, data['development_certificate_name'])
        self.assertEqual(config.development_bundle_identifier, data['development_bundle_identifier'])

    def test_file_upload_with_invalid_content_type(self):
        image = SimpleUploadedFile('test.jpg', b'content', content_type='image/jpeg')
        response = self.client.put(self.url, {'production_certificate': image}, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue('production_certificate' in response.data)

    def test_to_big_file_upload(self):
        cert = SimpleUploadedFile('test.p12', b'content' * 10000000, content_type='application/x-pkcs12')
        response = self.client.put(self.url, {'production_certificate': cert}, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue('production_certificate' in response.data)

    def test_remove_certificate(self):
        self.config.production_certificate = b'content'
        self.config.development_certificate = b'content'
        self.config.save()

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['production_certificate'])
        self.assertTrue(response.data['development_certificate'])

        data = {
            'production_certificate': True,
            'development_certificate': False
        }
        url = reverse('v1:apns-remove-certificate', args=(self.instance.name, ))
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data['production_certificate'])
        self.assertTrue(response.data['development_certificate'])

        data = {
            'development_certificate': True
        }
        response = self.client.post(url, data)
        self.assertFalse(response.data['production_certificate'])
        self.assertFalse(response.data['development_certificate'])
