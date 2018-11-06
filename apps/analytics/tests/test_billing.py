from datetime import date
from unittest import mock

from django.test import TestCase, override_settings
from django_dynamic_fixture import G

from apps.admins.models import Admin
from apps.analytics.tasks import (
    NotifyAboutHardLimitReached,
    NotifyAboutPaymentFailure,
    NotifyAboutPaymentReceived,
    NotifyAboutSoftLimitReached
)
from apps.billing.models import Invoice
from apps.core.tests.mixins import CleanupTestCaseMixin


@override_settings(POST_TRANSACTION_SUCCESS_EAGER=True)
class TestNotifyAboutLimitReached(CleanupTestCaseMixin, TestCase):
    def setUp(self):
        self.admin = G(Admin)

    @mock.patch('apps.analytics.tasks.analytics.track')
    def test_run_soft_limit(self, track_mock):
        self.assertFalse(track_mock.called)
        NotifyAboutSoftLimitReached.delay(self.admin.pk)
        self.assertTrue(track_mock.called)

    @mock.patch('apps.analytics.tasks.analytics.track')
    def test_run_hard_limit(self, track_mock):
        self.assertFalse(track_mock.called)
        NotifyAboutHardLimitReached.delay(self.admin.pk)
        self.assertTrue(track_mock.called)


@override_settings(POST_TRANSACTION_SUCCESS_EAGER=True)
class NotifyAboutPaymentReceivedTestCase(CleanupTestCaseMixin, TestCase):
    def setUp(self):
        self.invoice = G(Invoice, status=Invoice.STATUS_CHOICES.PAYMENT_SUCCEEDED)
        self.payment_date = date.today().isoformat()
        self.task = NotifyAboutPaymentReceived

    def test_invalid_invoice(self):
        with self.assertRaises(Invoice.DoesNotExist):
            self.task.delay('dummy', self.payment_date).get()

        with self.assertRaises(Invoice.DoesNotExist):
            self.task.delay(G(Invoice, status=Invoice.STATUS_CHOICES.NEW).reference, self.payment_date).get()

    @mock.patch('apps.analytics.tasks.analytics.track')
    def test_run(self, track_mock):
        self.assertFalse(track_mock.called)
        self.task.delay(self.invoice.reference, self.payment_date)
        self.assertEqual(track_mock.call_count, 1)


@override_settings(POST_TRANSACTION_SUCCESS_EAGER=True)
class NotifyAboutPaymentFailureTestCase(CleanupTestCaseMixin, TestCase):
    def setUp(self):
        self.invoice = G(Invoice, status=Invoice.STATUS_CHOICES.PAYMENT_FAILED)
        self.task = NotifyAboutPaymentFailure

    def test_invalid_invoice(self):
        with self.assertRaises(Invoice.DoesNotExist):
            self.task.delay('dummy').get()

        with self.assertRaises(Invoice.DoesNotExist):
            self.task.delay(G(Invoice, status=Invoice.STATUS_CHOICES.NEW).reference).get()

    @mock.patch('apps.analytics.tasks.analytics.track')
    def test_run(self, track_mock):
        self.assertFalse(track_mock.called)
        self.task.delay(self.invoice.reference)
        self.assertEqual(track_mock.call_count, 1)
