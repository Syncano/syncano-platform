# coding=UTF8
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from django_dynamic_fixture import G

from apps.admins.models import Admin
from apps.admins.tasks import RemoveBotAccounts


class TestBotCleanup(TestCase):
    def setUp(self):
        now = timezone.now()
        yesterday = now - timedelta(days=1)

        self.to_del = [
            G(Admin, email='syncano.bot+123@gmail.com', created_at=yesterday),
            G(Admin, email='syncano.bot+123@syncano.com', created_at=yesterday)
        ]
        self.to_keep = [
            G(Admin, email='syncano.bot+124@syncano.com', created_at=now),
            G(Admin, email='syncano.bot+billing@syncano.com', created_at=yesterday),
            G(Admin, email='syncano.bot+123@doe.com', created_at=yesterday)
        ]

    def test_cleanup(self):
        self.assertEqual(Admin.objects.count(), len(self.to_del) + len(self.to_keep))
        RemoveBotAccounts.delay()
        self.assertEqual(Admin.objects.count(), len(self.to_keep))
        ids = Admin.objects.values_list('id', flat=True)
        self.assertEqual(set(ids), set([admin.pk for admin in self.to_keep]))
