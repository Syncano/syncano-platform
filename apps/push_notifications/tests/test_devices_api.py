import uuid

from django.urls import reverse
from django_dynamic_fixture import G
from rest_framework import status

from apps.core.tests.testcases import SyncanoAPITestBase
from apps.instances.helpers import set_current_instance
from apps.push_notifications.models import APNSConfig, APNSDevice, APNSMessage, GCMConfig, GCMDevice, GCMMessage
from apps.users.models import User


class TestGCMDevicesListAPI(SyncanoAPITestBase):
    disable_user_profile = False

    def setUp(self):
        super().setUp()
        set_current_instance(self.instance)
        self.url = reverse('v1:gcm-devices-list', args=(self.instance.name, ))

    def test_if_can_retrieve_list(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_if_can_create_device(self):
        data = {
            'device_id': '0x1',
            'registration_id': '123'
        }
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        for k in data.keys():
            self.assertEqual(response.data[k], data[k])
        self.assertEqual(response.data['is_active'], True)
        self.assertEqual(response.data['user'], None)

        data = {
            'label': '',
            'device_id': '0x1',
            'registration_id': '124'
        }
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        for k in data.keys():
            self.assertEqual(response.data[k], data[k])

    def test_registration_id_validation(self):
        data = {
            'device_id': '0x1',
            'registration_id': '123'
        }
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # Validate uniqueness
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        # Validate charset
        data['registration_id'] = '|ID|1|:drtTv5631ew:APA91bEd4k'
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        data['registration_id'] = '|ID|1|:drtTv5631ew:APA91bEd4k/ablaespanol'
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_if_can_add_to_big_device_id(self):
        data = {
            'device_id': '0x8000000000000002',
            'registration_id': '123'
        }
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue('device_id' in response.data)

    def test_if_user_id_is_validated(self):
        data = {
            'device_id': '0x1',
            'registration_id': '123',
            'user': 1234567890
        }
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue('user' in response.data)

    def test_if_user_key_is_respected(self):
        api_key = self.instance.create_apikey()
        user_1 = G(User)
        user_2 = G(User)
        headers = {
            'HTTP_X_API_KEY': api_key.key,
            'HTTP_X_USER_KEY': user_1.key,
        }

        G(GCMDevice, user=user_1)
        G(GCMDevice, user=user_2)

        response = self.client.get(self.url, **headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['objects']), 1)
        self.assertEqual(response.data['objects'][0]['user'], user_1.pk)

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['objects']), 2)
        self.assertEqual(response.data['objects'][0]['user'], user_1.pk)
        self.assertEqual(response.data['objects'][1]['user'], user_2.pk)

    def test_if_user_is_fulfilled(self):
        api_key = self.instance.create_apikey()
        user = G(User)
        headers = {
            'HTTP_X_API_KEY': api_key.key,
            'HTTP_X_USER_KEY': user.key,
        }
        data = {
            'device_id': '0x1',
            'registration_id': '123'
        }
        response = self.client.post(self.url, data, **headers)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['device_id'], data['device_id'])
        self.assertEqual(response.data['registration_id'], data['registration_id'])
        self.assertEqual(response.data['is_active'], True)
        self.assertEqual(response.data['user'], user.pk)

    def test_user_filter(self):
        user_1 = G(User)
        user_2 = G(User)

        G(GCMDevice, user=user_1)
        G(GCMDevice, user=user_2)
        G(GCMDevice, user=user_2)

        response = self.client.get(self.url, {'user': user_1.pk})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['objects']), 1)
        self.assertEqual(response.data['objects'][0]['user'], user_1.pk)

        response = self.client.get(self.url, {'user': user_2.pk})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['objects']), 2)
        self.assertEqual(response.data['objects'][0]['user'], user_2.pk)
        self.assertEqual(response.data['objects'][1]['user'], user_2.pk)

    def test_device_id_filter(self):
        G(GCMDevice, device_id='0xaaa')
        G(GCMDevice, device_id='0xbbb')
        G(GCMDevice, device_id='0xbbb')

        response = self.client.get(self.url, {'device_id': '0xaaa'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['objects']), 1)
        self.assertEqual(response.data['objects'][0]['device_id'], '0xaaa')

        response = self.client.get(self.url, {'device_id': 'bbb'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['objects']), 2)
        self.assertEqual(response.data['objects'][0]['device_id'], '0xbbb')
        self.assertEqual(response.data['objects'][1]['device_id'], '0xbbb')

        response = self.client.get(self.url, {'device_id': 'egg'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_is_active_filter(self):
        G(GCMDevice, is_active=True)
        G(GCMDevice, is_active=False)
        G(GCMDevice, is_active=False)

        for value in ('true', 'True', 't', 'T'):
            self.assert_is_active_filtering(is_active=value, device_count=1)

        for value in ('false', 'False', 'f', 'F'):
            self.assert_is_active_filtering(is_active=value, device_count=2)

    def assert_is_active_filtering(self, is_active, device_count):
        BOOLEAN_MAP = {
            'True': True,
            'False': False,
            'true': True,
            'false': False,
            'T': True,
            'F': False,
            't': True,
            'f': False
        }

        response = self.client.get(self.url, {'is_active': is_active})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['objects']), device_count)
        for device in response.data['objects']:
            self.assertEqual(device['is_active'], BOOLEAN_MAP[is_active])


class TestGCMDevicesDetailAPI(SyncanoAPITestBase):
    disable_user_profile = False

    def setUp(self):
        super().setUp()
        set_current_instance(self.instance)
        self.device = G(GCMDevice)
        self.device.refresh_from_db()
        self.url = reverse('v1:gcm-devices-detail', args=(self.instance.name, self.device.registration_id))
        self.config = GCMConfig.objects.create(development_api_key='123qwe')

    def test_if_can_retrieve_device(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['registration_id'], self.device.registration_id)
        self.assertEqual(response.data['device_id'], self.device.device_id)

    def test_retrieving_long_registration_id(self):
        device = G(GCMDevice, registration_id='|ID|1|:drtTv5631ew:APA91bEd4k')
        url = reverse('v1:gcm-devices-detail', args=(self.instance.name, device.registration_id))
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['registration_id'], device.registration_id)

    def test_if_can_delete_device(self):
        device = G(GCMDevice)
        url = reverse('v1:gcm-devices-detail', args=(self.instance.name, device.registration_id))
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(GCMDevice.objects.filter(pk=device.pk).count(), 0)

    def test_if_can_partial_update_device(self):
        data = {'label': 'test123'}
        response = self.client.patch(self.url, data)
        device = GCMDevice.objects.get(pk=self.device.pk)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(device.registration_id, self.device.registration_id)
        self.assertEqual(device.device_id, self.device.device_id)
        self.assertEqual(device.label, data['label'])

    def test_if_can_update_device(self):
        data = {
            'label': 'test123',
            'device_id': '0x2'
        }
        response = self.client.patch(self.url, data)
        device = GCMDevice.objects.get(pk=self.device.pk)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(device.label, data['label'])
        self.assertEqual(device.device_id, data['device_id'])

    def test_if_cant_update_registration_id(self):
        data = {'registration_id': 'new_one'}
        response = self.client.patch(self.url, data)
        device = GCMDevice.objects.get(pk=self.device.pk)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(device.registration_id, self.device.registration_id)
        self.assertNotEqual(device.registration_id, data['registration_id'])

    def test_if_can_send_message_to_device(self):
        url = reverse('v1:gcm-devices-send-message', args=(self.instance.name, self.device.registration_id))
        data = {'content': {'environment': 'development'}}

        self.assertEqual(GCMMessage.objects.count(), 0)
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue('content' in response.data)
        self.assertTrue('environment' in response.data['content'])
        self.assertTrue('registration_ids' in response.data['content'])
        self.assertEqual(response.data['content']['environment'], data['content']['environment'])
        self.assertEqual(response.data['content']['registration_ids'], [self.device.registration_id])
        self.assertEqual(GCMMessage.objects.count(), 1)

    def test_if_empty_data_in_send_message_do_not_raise_500(self):
        url = reverse('v1:gcm-devices-send-message', args=(self.instance.name, self.device.registration_id))
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_if_user_cant_change_user(self):
        api_key = self.instance.create_apikey()
        user = G(User)
        device = G(GCMDevice, user=user)
        headers = {
            'HTTP_X_API_KEY': api_key.key,
            'HTTP_X_USER_KEY': user.key,
        }

        url = reverse('v1:gcm-devices-detail', args=(self.instance.name, device.registration_id))
        response = self.client.patch(url, {'user': 1}, **headers)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue('user' in response.data)


class TestAPNSDevicesListAPI(SyncanoAPITestBase):
    disable_user_profile = False

    def setUp(self):
        super().setUp()
        set_current_instance(self.instance)
        self.url = reverse('v1:apns-devices-list', args=(self.instance.name, ))

    def test_if_can_retrieve_list(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_if_can_create_device(self):
        data = {
            'device_id': str(uuid.uuid4()),
            'registration_id': '02B02B02B002B02B02B002B02B02B002B02B02B002B02B02B03A03A03A000000'
        }
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['device_id'], data['device_id'])
        self.assertEqual(response.data['registration_id'], data['registration_id'])
        self.assertEqual(response.data['is_active'], True)
        self.assertEqual(response.data['user'], None)

    def test_if_user_id_is_validated(self):
        data = {
            'device_id': str(uuid.uuid4()),
            'registration_id': '02B02B02B002B02B02B002B02B02B002B02B02B002B02B02B03A03A03A000000',
            'user': 1234567890
        }
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue('user' in response.data)

    def test_if_user_key_is_respected(self):
        api_key = self.instance.create_apikey()
        user_1 = G(User)
        user_2 = G(User)
        headers = {
            'HTTP_X_API_KEY': api_key.key,
            'HTTP_X_USER_KEY': user_1.key,
        }

        G(APNSDevice, user=user_1)
        G(APNSDevice, user=user_2)

        response = self.client.get(self.url, **headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['objects']), 1)
        self.assertEqual(response.data['objects'][0]['user'], user_1.pk)

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['objects']), 2)
        self.assertEqual(response.data['objects'][0]['user'], user_1.pk)
        self.assertEqual(response.data['objects'][1]['user'], user_2.pk)

    def test_if_user_is_fulfilled(self):
        api_key = self.instance.create_apikey()
        user = G(User)
        headers = {
            'HTTP_X_API_KEY': api_key.key,
            'HTTP_X_USER_KEY': user.key,
        }
        data = {
            'device_id': str(uuid.uuid4()),
            'registration_id': '02B02B02B002B02B02B002B02B02B002B02B02B002B02B02B03A03A03A000000'
        }
        response = self.client.post(self.url, data, **headers)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['device_id'], data['device_id'])
        self.assertEqual(response.data['registration_id'], data['registration_id'])
        self.assertEqual(response.data['is_active'], True)
        self.assertEqual(response.data['user'], user.pk)

    def test_user_filter(self):
        user_1 = G(User)
        user_2 = G(User)

        G(APNSDevice, user=user_1)
        G(APNSDevice, user=user_2)
        G(APNSDevice, user=user_2)

        response = self.client.get(self.url, {'user': user_1.pk})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['objects']), 1)
        self.assertEqual(response.data['objects'][0]['user'], user_1.pk)

        response = self.client.get(self.url, {'user': user_2.pk})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['objects']), 2)
        self.assertEqual(response.data['objects'][0]['user'], user_2.pk)
        self.assertEqual(response.data['objects'][1]['user'], user_2.pk)

    def test_device_id_filter(self):
        id_1 = str(uuid.uuid4())
        id_2 = str(uuid.uuid4())

        G(APNSDevice, device_id=id_1)
        G(APNSDevice, device_id=id_2)
        G(APNSDevice, device_id=id_2)

        response = self.client.get(self.url, {'device_id': id_1})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['objects']), 1)
        self.assertEqual(response.data['objects'][0]['device_id'], id_1)

        response = self.client.get(self.url, {'device_id': id_2})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['objects']), 2)
        self.assertEqual(response.data['objects'][0]['device_id'], id_2)
        self.assertEqual(response.data['objects'][1]['device_id'], id_2)

        response = self.client.get(self.url, {'device_id': 'abc'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_is_active_filter(self):
        G(APNSDevice, is_active=True)
        G(APNSDevice, is_active=False)
        G(APNSDevice, is_active=False)

        response = self.client.get(self.url, {'is_active': True})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['objects']), 1)
        self.assertEqual(response.data['objects'][0]['is_active'], True)

        response = self.client.get(self.url, {'is_active': False})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['objects']), 2)
        self.assertEqual(response.data['objects'][0]['is_active'], False)
        self.assertEqual(response.data['objects'][1]['is_active'], False)


class TestAPNSDevicesDetailAPI(SyncanoAPITestBase):
    disable_user_profile = False

    def setUp(self):
        super().setUp()
        set_current_instance(self.instance)
        self.device = G(APNSDevice)
        self.url = reverse('v1:apns-devices-detail', args=(self.instance.name, self.device.registration_id))
        self.config = APNSConfig.objects.create(
            development_certificate_name='123qwe',
            development_certificate=b'content',
            development_bundle_identifier='123qwe',
        )

    def test_if_can_retrieve_device(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['registration_id'], self.device.registration_id)
        self.assertEqual(response.data['device_id'], str(self.device.device_id))

    def test_if_can_delete_device(self):
        device = G(APNSDevice)
        url = reverse('v1:apns-devices-detail', args=(self.instance.name, device.registration_id))
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(APNSDevice.objects.filter(pk=device.pk).count(), 0)

    def test_if_can_partial_update_device(self):
        data = {'label': 'test123'}
        response = self.client.patch(self.url, data)
        device = APNSDevice.objects.get(pk=self.device.pk)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(device.registration_id, self.device.registration_id)
        self.assertEqual(device.device_id, self.device.device_id)
        self.assertEqual(device.label, data['label'])

    def test_if_can_update_device(self):
        data = {
            'label': 'test123',
            'device_id': str(uuid.uuid4())
        }
        response = self.client.patch(self.url, data)
        device = APNSDevice.objects.get(pk=self.device.pk)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(device.label, data['label'])
        self.assertEqual(str(device.device_id), data['device_id'])

    def test_if_cant_update_registration_id(self):
        data = {'registration_id': '0AB02B02B002B02B02B002B02B02B002B02B02B002B02B02B03A03A03A000000'}
        response = self.client.patch(self.url, data)
        device = APNSDevice.objects.get(pk=self.device.pk)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(device.registration_id, self.device.registration_id)
        self.assertNotEqual(device.registration_id, data['registration_id'])

    def test_if_can_send_message_to_device(self):
        url = reverse('v1:apns-devices-send-message', args=(self.instance.name, self.device.registration_id))
        data = {'content': {'environment': 'development', 'aps': {'alert': 'TestAlert'}}}

        self.assertEqual(APNSMessage.objects.count(), 0)
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue('content' in response.data)
        self.assertTrue('environment' in response.data['content'])
        self.assertTrue('registration_ids' in response.data['content'])
        self.assertEqual(response.data['content']['environment'], data['content']['environment'])
        self.assertEqual(response.data['content']['registration_ids'], [self.device.registration_id])
        self.assertEqual(APNSMessage.objects.count(), 1)

    def test_if_empty_data_in_send_message_do_not_raise_500(self):
        url = reverse('v1:apns-devices-send-message', args=(self.instance.name, self.device.registration_id))
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_if_user_cant_change_user(self):
        api_key = self.instance.create_apikey()
        user = G(User)
        device = G(APNSDevice, user=user)
        headers = {
            'HTTP_X_API_KEY': api_key.key,
            'HTTP_X_USER_KEY': user.key,
        }

        url = reverse('v1:apns-devices-detail', args=(self.instance.name, device.registration_id))
        response = self.client.patch(url, {'user': 1}, **headers)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue('user' in response.data)
