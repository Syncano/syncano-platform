from unittest import mock

from django.conf import settings
from django.test import TestCase
from django.urls import reverse
from django_dynamic_fixture import G

from apps.admins.models import Admin
from apps.billing.models import Subscription
from apps.core.tests.mixins import CleanupTestCaseMixin

from ..tasks import (
    AdminStateUpdater,
    NotifyAboutAdminActivation,
    NotifyAboutAdminPasswordReset,
    NotifyAboutAdminSignup,
    NotifyAboutLogIn,
    NotifyAboutLogInFailure,
    NotifyAboutPlanChange
)


class TestNotifyTasks(CleanupTestCaseMixin, TestCase):
    url = reverse('v1:authenticate')

    def setUp(self):
        self.admin = G(Admin, email='john@doe.com', is_active=False)

    @mock.patch('apps.analytics.tasks.analytics')
    def test_notify_about_signup(self, analytics_mock):
        NotifyAboutAdminSignup.delay(self.admin.id, self.admin.email,
                                     self.admin.created_at.strftime(settings.DATETIME_FORMAT))
        self.assertTrue(analytics_mock.track.called)
        self.assertTrue(analytics_mock.identify.called)

    @mock.patch('apps.analytics.tasks.analytics')
    def test_notify_about_activation(self, analytics_mock):
        NotifyAboutAdminActivation.delay(self.admin.pk, 'uid', self.admin.email, 'token')
        self.assertTrue(analytics_mock.track.called)
        self.assertTrue(analytics_mock.identify.called)

    @mock.patch('apps.analytics.tasks.analytics')
    def test_notify_about_admin_password_reset(self, analytics_mock):
        NotifyAboutAdminPasswordReset.delay(self.admin.id, 'uid', 'token')
        self.assertTrue(analytics_mock.track.called)

    @mock.patch('apps.analytics.tasks.analytics')
    def test_notify_about_login(self, analytics_mock):
        NotifyAboutLogIn.delay(self.admin.id, self.admin.email, 'password')
        self.assertTrue(analytics_mock.track.called)

    @mock.patch('apps.analytics.tasks.analytics')
    def test_notify_about_login_failure(self, analytics_mock):
        NotifyAboutLogInFailure.delay(self.admin.id, self.admin.email, 'password')
        self.assertTrue(analytics_mock.track.called)

    @mock.patch('apps.analytics.tasks.analytics')
    def test_admin_stats_updater(self, analytics_mock):
        AdminStateUpdater.delay()
        self.assertEqual(analytics_mock.identify.call_count, 1)

        analytics_mock.reset_mock()
        G(Admin, email='john2@doe.com')
        AdminStateUpdater.delay()
        self.assertEqual(analytics_mock.identify.call_count, 2)

    @mock.patch('apps.analytics.tasks.AdminStateUpdater.delay')
    def test_admin_stats_updater_reschedule(self, task_mock):
        G(Admin, email='john2@doe.com')
        AdminStateUpdater.run()
        self.assertFalse(task_mock.called)

        with mock.patch('apps.analytics.tasks.AdminStateUpdater.chunk_size', 1):
            AdminStateUpdater.run()
            task_mock.assert_called_once_with(last_pk=self.admin.pk)

    @mock.patch('apps.analytics.tasks.analytics')
    def test_notify_about_plan_change(self, notify_task_mock):
        subscription = Subscription.objects.active_for_admin(self.admin).get()
        NotifyAboutPlanChange.delay(subscription_pk=subscription.pk)
        self.assertTrue(notify_task_mock.track.called)
