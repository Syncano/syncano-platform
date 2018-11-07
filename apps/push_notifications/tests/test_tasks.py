import binascii
from ssl import SSLError
from time import time
from unittest import mock

from django_dynamic_fixture import G
from gcm.gcm import GCMAuthenticationException
from rest_framework.test import APITestCase

from apps.core.tests.mixins import CleanupTestCaseMixin
from apps.core.tests.testcases import SyncanoAPITestBase
from apps.instances.helpers import set_current_instance
from apps.instances.models import Instance, InstanceIndicator
from apps.push_notifications.apns.exceptions import APNSServerError
from apps.push_notifications.models import APNSConfig, APNSDevice, APNSMessage, GCMConfig, GCMDevice, GCMMessage
from apps.push_notifications.tasks import APNSFeedbackDispatcher, GetAPNSFeedback, SendAPNSMessage, SendGCMMessage


class TestSendGCMMessageTask(SyncanoAPITestBase):
    disable_user_profile = False

    def setUp(self):
        super().setUp()
        set_current_instance(self.instance)

        self.devices = [
            G(GCMDevice, registration_id='a'),
            G(GCMDevice, registration_id='b'),
            G(GCMDevice, registration_id='c'),
        ]
        self.config = G(GCMConfig, development_api_key='test')
        self.message = G(GCMMessage, content={
            'environment': 'development',
            'registration_ids': [device.registration_id for device in self.devices]
        })
        self.task = SendGCMMessage
        self.task.instance = self.instance
        self.task.request.kwargs = {'instance_id': self.instance.pk}

    def test_run_with_empty_config(self):
        GCMConfig.objects.filter(pk=self.config.pk).update(development_api_key='')

        self.task.run(self.message.pk, instance_pk=self.instance.pk)
        self.message.refresh_from_db()
        self.assertEqual(self.message.status, GCMMessage.STATUSES.ERROR)
        self.assertEqual(self.message.result, 'GCM api key for "development" environment is required.')

    @mock.patch('apps.push_notifications.tasks.GCM.json_request')
    def test_run_with_error_status(self, json_request_mock):
        json_request_mock.return_value = {'errors': {
            'NotRegistered': ['a', 'b', 'c']
        }}
        self.assertFalse(json_request_mock.called)
        self.task.run(self.message.pk, instance_pk=self.instance.pk)
        self.message.refresh_from_db()

        self.assertTrue(json_request_mock.called)
        self.assertEqual(self.message.status, GCMMessage.STATUSES.ERROR)
        self.assertEqual(self.message.result, json_request_mock.return_value)

    @mock.patch('apps.push_notifications.tasks.GCM.json_request')
    def test_run_with_delivered_status(self, json_request_mock):
        json_request_mock.return_value = {'canonical': {
            'a': 'canonical_a'
        }}
        self.assertFalse(json_request_mock.called)
        self.task.run(self.message.pk, instance_pk=self.instance.pk)
        self.message.refresh_from_db()

        self.assertTrue(json_request_mock.called)
        self.assertEqual(self.message.status, GCMMessage.STATUSES.DELIVERED)
        self.assertEqual(self.message.result, json_request_mock.return_value)

    @mock.patch('apps.push_notifications.tasks.GCM.json_request')
    def test_run_with_partially_delivered_status(self, json_request_mock):
        json_request_mock.return_value = {'errors': {
            'NotRegistered': ['a']
        }}
        self.assertFalse(json_request_mock.called)
        self.task.run(self.message.pk, instance_pk=self.instance.pk)
        self.message.refresh_from_db()

        self.assertTrue(json_request_mock.called)
        self.assertEqual(self.message.status, GCMMessage.STATUSES.PARTIALLY_DELIVERED)
        self.assertEqual(self.message.result, json_request_mock.return_value)

    @mock.patch('apps.push_notifications.tasks.GCM.json_request')
    def test_run_with_gcm_exception(self, json_request_mock):
        error = 'oh noes'
        json_request_mock.side_effect = GCMAuthenticationException(error)
        self.task.run(self.message.pk, instance_pk=self.instance.pk)
        self.message.refresh_from_db()

        self.assertTrue(json_request_mock.called)
        self.assertEqual(self.message.status, GCMMessage.STATUSES.ERROR)
        self.assertEqual(self.message.result, error)

    @mock.patch('apps.push_notifications.tasks.GCM.json_request')
    @mock.patch('apps.push_notifications.tasks.SendGCMMessage.get_logger', mock.MagicMock())
    def test_run_with_unhandled_exception(self, json_request_mock):
        json_request_mock.side_effect = Exception('oh noes')
        self.task.run(self.message.pk, instance_pk=self.instance.pk)
        self.message.refresh_from_db()

        self.assertTrue(json_request_mock.called)
        self.assertEqual(self.message.status, GCMMessage.STATUSES.ERROR)
        self.assertEqual(self.message.result, 'Internal server error.')


class TestSendAPNSMessageTask(SyncanoAPITestBase):

    def setUp(self):
        super().setUp()
        set_current_instance(self.instance)

        self.config = G(APNSConfig)
        self.message = G(APNSMessage, content={
            'environment': 'development',
            'registration_ids': [
                '02B02B02B002B02B02B002B02B02B002B02B02B002B02B02B03A03A03A000000'
            ],
            'aps': {'alert': 'test'}
        })
        self.task = SendAPNSMessage
        self.task.instance = self.instance
        self.task.request.kwargs = {'instance_id': self.instance.pk}

    def test_run_with_empty_config(self):
        APNSConfig.objects.filter(pk=self.config.pk).update(development_certificate=None)

        self.task.run(self.message.pk, instance_pk=self.instance.pk)
        self.message.refresh_from_db()
        self.assertEqual(self.message.status, APNSMessage.STATUSES.ERROR)
        self.assertEqual(self.message.result, 'APNS certificate for "development" environment is required.')

    @mock.patch('apps.push_notifications.tasks.APNSPushSocket.send')
    @mock.patch('apps.push_notifications.tasks.Cached.get')
    @mock.patch('apps.push_notifications.tasks.crypto')
    @mock.patch('apps.push_notifications.apns.sockets.ssl.wrap_socket', mock.MagicMock())
    def test_run_with_delivered_status(self, crypto_mock, get_mock, send_mock):
        get_mock.return_value = mock.Mock()
        crypto_mock.load_pkcs12 = mock.MagicMock()
        crypto_mock.dump_certificate.return_value = 'a'
        crypto_mock.dump_privatekey.return_value = 'a'

        self.assertFalse(send_mock.called)
        self.assertFalse(crypto_mock.dump_certificate.called)
        self.assertFalse(crypto_mock.dump_privatekey.called)
        self.task.run(self.message.pk, instance_pk=self.instance.pk)
        self.assertTrue(send_mock.called)
        self.assertTrue(crypto_mock.load_pkcs12.called)
        self.assertTrue(crypto_mock.dump_certificate.called)
        self.assertTrue(crypto_mock.dump_privatekey.called)

    @mock.patch('apps.push_notifications.tasks.SendAPNSMessage.make_request')
    @mock.patch('apps.push_notifications.tasks.crypto.load_pkcs12', mock.MagicMock())
    @mock.patch('apps.push_notifications.tasks.SendAPNSMessage.get_logger', mock.MagicMock())
    def test_run_with_exception(self, make_request_mock):
        for exception, expected_result in (
            (APNSServerError('status', 'identifier'), {'description': 'None (unknown)',
                                                       'identifier': 'identifier',
                                                       'status': 'status'}),
            (SSLError('oh noes'), 'Invalid certificate.'),
            (TypeError(), 'Invalid registration_id value.'),
            (Exception('oh noes'), 'Internal server error.')
        ):
            make_request_mock.side_effect = exception
            self.task.run(self.message.pk, instance_pk=self.instance.pk)
            self.message.refresh_from_db()

            self.assertTrue(make_request_mock.called)
            self.assertEqual(self.message.status, APNSMessage.STATUSES.ERROR)
            self.assertEqual(self.message.result, expected_result)


class TestAPNSFeedbackDispatcherTask(CleanupTestCaseMixin, APITestCase):

    def setUp(self):
        super().setUp()

        _type = InstanceIndicator.TYPES.APNS_DEVICES_COUNT

        self.instances = [G(Instance), G(Instance), G(Instance)]
        InstanceIndicator.objects.filter(instance=self.instances[0], type=_type).update(value=10)
        InstanceIndicator.objects.filter(instance=self.instances[1], type=_type).update(value=10)
        self.task = APNSFeedbackDispatcher

    @mock.patch('apps.push_notifications.tasks.GetAPNSFeedback.delay')
    def test_run(self, delay_mock):
        self.assertFalse(delay_mock.called)
        self.task.run()
        self.assertTrue(delay_mock.called)
        self.assertEqual(delay_mock.call_count, 4)

        delay_mock.assert_any_call('production', instance_pk=self.instances[0].pk)
        delay_mock.assert_any_call('development', instance_pk=self.instances[0].pk)
        delay_mock.assert_any_call('production', instance_pk=self.instances[1].pk)
        delay_mock.assert_any_call('development', instance_pk=self.instances[1].pk)


class TestGetAPNSFeedbackTask(SyncanoAPITestBase):
    disable_user_profile = False

    def setUp(self):
        super().setUp()
        set_current_instance(self.instance)

        self.config = G(APNSConfig)
        self.devices = [
            G(APNSDevice, registration_id='a' * 64),
            G(APNSDevice, registration_id='b' * 64)
        ]

        self.environment = 'development'
        self.task = GetAPNSFeedback
        self.task.instance = self.instance
        self.task.request.kwargs = {'instance_id': self.instance.pk}

    @mock.patch('apps.push_notifications.tasks.GetAPNSFeedback.get_logger')
    def test_run_with_empty_config(self, logger_mock):
        APNSConfig.objects.filter(pk=self.config.pk).update(development_certificate=None)
        self.task.run(self.environment, instance_pk=self.instance.pk)
        self.assertTrue(logger_mock().warning.called)

    @mock.patch('apps.push_notifications.tasks.APNSFeedbackSocket.read')
    @mock.patch('apps.push_notifications.tasks.Cached.get')
    @mock.patch('apps.push_notifications.tasks.crypto')
    @mock.patch('apps.push_notifications.apns.sockets.ssl.wrap_socket', mock.MagicMock())
    def test_run(self, crypto_mock, get_mock, read_mock):
        get_mock.return_value = mock.Mock()
        crypto_mock.load_pkcs12 = mock.MagicMock()
        crypto_mock.dump_certificate.return_value = 'a'
        crypto_mock.dump_privatekey.return_value = 'a'
        read_mock.return_value = [(time(), binascii.unhexlify(device.registration_id)) for device in self.devices]

        self.assertFalse(read_mock.called)
        self.assertFalse(crypto_mock.dump_certificate.called)
        self.assertFalse(crypto_mock.dump_privatekey.called)
        self.task.run(self.environment, instance_pk=self.instance.pk)
        self.assertTrue(read_mock.called)
        self.assertTrue(crypto_mock.load_pkcs12.called)
        self.assertTrue(crypto_mock.dump_certificate.called)
        self.assertTrue(crypto_mock.dump_privatekey.called)

        ids = [device.pk for device in self.devices]
        inactive_devices = APNSDevice.objects.filter(pk__in=ids, is_active=False).count()
        self.assertEqual(inactive_devices, 2)
