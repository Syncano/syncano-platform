# coding=UTF8

from datetime import timedelta
from unittest import mock

from django.conf import settings
from django.test import TransactionTestCase, override_settings
from django.utils import timezone

from apps.admins.models import Admin
from apps.admins.tasks import DeleteInactiveAccounts
from apps.analytics.tasks import SendUnusedAccountNotification
from apps.instances.models import Instance


class TestDeleteNotification(TransactionTestCase):
    """
    We have to use TransactionTestCase because postgresql
    does not support DDL and DML statements on same data in one transaction.
    Thanks to using TransactionTestCase. every method is run in separate
    DB transaction.
    """

    fixtures = ['core_data.json']

    def setUp(self):
        self.admin = Admin.objects.create(email='john@doe.com', is_active=True)
        self.instance = Instance(name='testinstance2', description='desc2',
                                 owner=self.admin)
        self.instance.save()

    @override_settings(ACCOUNT_MAX_IDLE_DAYS=90)
    @mock.patch('analytics.track')
    def test_notifications(self, track_mock):
        self.admin.last_access = timezone.now() - timedelta(days=settings.ACCOUNT_MAX_IDLE_DAYS) - timedelta(days=1)
        self.admin.save()
        SendUnusedAccountNotification.delay()
        self.admin.refresh_from_db()
        self.assertNotEqual(self.admin.noticed_at, None)
        self.assertTrue(track_mock.called)
        self.assertIsNotNone(track_mock.call_args[0][2].get('link'))

    @override_settings(ACCOUNT_MAX_IDLE_DAYS=90)
    def test_delete(self):
        now = timezone.now()
        self.admin.noticed_at = now - timedelta(days=settings.ACCOUNT_NOTICE_CONFIRMATION_DAYS) - timedelta(days=1)
        self.admin.save()
        DeleteInactiveAccounts.delay()
        self.assertFalse(Instance.objects.filter(pk=self.instance.pk).exists())
        self.assertFalse(Admin.objects.filter(pk=self.admin.pk).exists())

    @override_settings(ACCOUNT_MAX_IDLE_DAYS=90)
    @mock.patch('analytics.track')
    def test_staff_instances(self, track_mock):
        self.admin.last_access = timezone.now() - timedelta(days=settings.ACCOUNT_MAX_IDLE_DAYS) - timedelta(days=1)
        self.admin.save()
        self.admin.is_staff = True
        self.admin.save()
        self.assertTrue(Instance.objects.filter(owner__is_staff=True).exists())
        SendUnusedAccountNotification.delay()
        self.instance.refresh_from_db()
        self.assertEqual(self.admin.noticed_at, None)
        self.assertFalse(track_mock.called)
