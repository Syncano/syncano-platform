from datetime import datetime, timedelta
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework.serializers import ValidationError

from apps.push_notifications.validators import APNSCertificateValidator


class TestAPNSCertificateValidator(TestCase):

    def setUp(self):
        self.validator = APNSCertificateValidator('Production')
        self.certificate = SimpleUploadedFile('test.p12', b'content', content_type='application/x-pkcs12')

    def test_file_validation(self):
        with self.assertRaises(ValidationError):
            self.validator(self.certificate)

    def test_invalid_friendlyname(self):
        with self.assertRaises(ValidationError):
            self.validator.check_friendlyname('dummy')

    def test_invalid_type_of_friendlyname(self):
        with self.assertRaises(ValidationError):
            self.validator.check_friendlyname('Apple Development IOS Push Services: com.syncano.testApp')

    def test_valid_friendlyname_new_type(self):
        _type, bundle = self.validator.check_friendlyname(b'Apple Push Services: com.syncano.testApp')
        self.assertEqual(_type, None)
        self.assertEqual(bundle, 'com.syncano.testApp')

    def test_valid_friendlyname(self):
        _type, bundle = self.validator.check_friendlyname(b'Apple Production IOS Push Services: com.syncano.testApp')
        self.assertEqual(_type, 'Production')
        self.assertEqual(bundle, 'com.syncano.testApp')

    def test_empty_expiration_date(self):
        with self.assertRaises(ValidationError):
            self.validator.check_expiration_date(None)

    def test_dummy_expiration_date(self):
        with self.assertRaises(ValidationError):
            self.validator.check_expiration_date('dummy')

    def test_expired_expiration_date(self):
        expiration_date = datetime.today() - timedelta(days=1)
        with self.assertRaises(ValidationError):
            self.validator.check_expiration_date(expiration_date.strftime('%Y%m%d%H%M%SZ'))

    def test_valid_expiration_date(self):
        expiration_date = datetime.today() + timedelta(days=1)
        expected_date = self.validator.check_expiration_date(expiration_date.strftime('%Y%m%d%H%M%SZ'))
        self.assertEqual(expiration_date.strftime('%Y%m%d%H%M%S'), expected_date.strftime('%Y%m%d%H%M%S'))

    @mock.patch('apps.push_notifications.validators.crypto')
    def test_validation(self, crypto_mock):
        load_pkcs12 = mock.Mock()
        load_pkcs12.return_value = load_pkcs12
        load_pkcs12.get_friendlyname.return_value = 'Apple Production IOS Push Services: com.syncano.testApp'
        load_certificate = mock.Mock()
        load_certificate.return_value = load_certificate
        load_certificate.get_notAfter.return_value = (datetime.today() + timedelta(days=1)).strftime('%Y%m%d%H%M%SZ')
        crypto_mock.load_pkcs12.return_value = load_pkcs12
        crypto_mock.load_certificate.return_value = load_certificate

        self.assertFalse(crypto_mock.load_pkcs12.called)
        self.assertFalse(crypto_mock.load_certificate.called)
        self.assertFalse(load_pkcs12.get_friendlyname.called)
        self.assertFalse(load_certificate.get_notAfter.called)
        self.assertEqual(getattr(self.certificate, '_certificate_type', None), None)
        self.assertEqual(getattr(self.certificate, '_certificate_bundle', None), None)
        self.assertEqual(getattr(self.certificate, '_certificate_expiration', None), None)

        self.validator(self.certificate)

        self.assertTrue(crypto_mock.load_pkcs12.called)
        self.assertTrue(crypto_mock.load_certificate.called)
        self.assertTrue(load_pkcs12.get_friendlyname.called)
        self.assertTrue(load_certificate.get_notAfter.called)
        self.assertEqual(self.certificate._certificate_type, 'Production')
        self.assertEqual(self.certificate._certificate_bundle, 'com.syncano.testApp')
        self.assertEqual(
            self.certificate._certificate_expiration.strftime('%Y%m%d%H%M%SZ'),
            load_certificate.get_notAfter.return_value)
