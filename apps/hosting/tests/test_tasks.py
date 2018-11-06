import subprocess
from unittest import mock

from django.conf import settings
from django.db.models.signals import post_save, pre_save
from django_dynamic_fixture import G
from dns.resolver import NoAnswer
from munch import Munch

from apps.core.contextmanagers import ignore_signal
from apps.core.tests.testcases import SyncanoAPITestBase
from apps.hosting.exceptions import CNameNotSet, WrongCName
from apps.hosting.models import Hosting
from apps.hosting.tasks import (
    REMOVE_SSL_CERT_SCRIPT,
    RENEW_SSL_CERT_SCRIPT,
    HostingAddSecureCustomDomainTask,
    HostingRefreshSecureCustomDomainCertTask
)
from apps.instances.helpers import set_current_instance

TEST_DOMAIN = 'test.io'


class TestHostingDomainTasks(SyncanoAPITestBase):

    def setUp(self):
        super().setUp()
        self.hosting = G(Hosting, name='test_name', description='test_description', is_default=True)

    @mock.patch('apps.hosting.tasks.resolver.query')
    def test_domain_validation(self, query_mock):
        task = HostingAddSecureCustomDomainTask
        task.instance = self.instance

        query_mock.return_value = []
        self.assertRaises(WrongCName, task.validate_domain, TEST_DOMAIN)
        query_mock.assert_called_once_with(TEST_DOMAIN, 'CNAME')

        query_mock.side_effect = NoAnswer()
        query_mock.reset_mock()
        self.assertRaises(CNameNotSet, task.validate_domain, TEST_DOMAIN)
        query_mock.assert_called_once_with(TEST_DOMAIN, 'CNAME')

        query_mock.reset_mock(side_effect=True)
        query_mock.return_value = [Munch(target=Munch(to_unicode=lambda: 'cname.response.'))]
        self.assertRaises(WrongCName, task.validate_domain, TEST_DOMAIN)

        query_mock.reset_mock()
        expected_cname = '{}{}.'.format(self.instance.name, settings.HOSTING_DOMAIN)
        query_mock.return_value = [Munch(target=Munch(to_unicode=lambda: expected_cname))]
        # This should not raise any error
        task.validate_domain(TEST_DOMAIN)

    @mock.patch('os.utime', mock.Mock())
    @mock.patch('apps.hosting.tasks.HostingAddSecureCustomDomainTask.delay', mock.Mock())
    @mock.patch('subprocess.check_output')
    def test_calling_refresh_cert_script(self, subprocess_mock):
        with ignore_signal(pre_save, post_save):
            self.instance.domains = [TEST_DOMAIN]
            self.instance.save()

            self.hosting.domains = [TEST_DOMAIN]
            self.hosting.ssl_status = Hosting.SSL_STATUSES.ON
            self.hosting.save()

        with mock.patch('os.path.exists', mock.Mock(return_value=True)):
            with mock.patch('os.listdir', mock.Mock(return_value=['.last_update', 'pem', TEST_DOMAIN])):
                HostingRefreshSecureCustomDomainCertTask.delay()
        self.assertEqual(subprocess_mock.call_args[0][0], [RENEW_SSL_CERT_SCRIPT, TEST_DOMAIN])
        set_current_instance(self.instance)
        self.hosting.refresh_from_db()
        self.assertEqual(self.hosting.ssl_status, Hosting.SSL_STATUSES.ON)

    @mock.patch('subprocess.check_output', mock.Mock(side_effect=subprocess.CalledProcessError(2, '')))
    @mock.patch('os.utime')
    def test_calling_refresh_cert_script_with_fresh_domain(self, utime_mock):
        with ignore_signal(pre_save, post_save):
            self.instance.domains = [TEST_DOMAIN]
            self.instance.save()

            self.hosting.domains = [TEST_DOMAIN]
            self.hosting.ssl_status = Hosting.SSL_STATUSES.ON
            self.hosting.save()

        with mock.patch('os.path.exists', mock.Mock(return_value=True)):
            with mock.patch('os.listdir', mock.Mock(return_value=[TEST_DOMAIN])):
                HostingRefreshSecureCustomDomainCertTask.delay()
        set_current_instance(self.instance)
        utime_mock.assert_called_once()

    @mock.patch('subprocess.check_output', mock.Mock(side_effect=[subprocess.CalledProcessError(1, ''),
                                                                  mock.Mock()]))
    @mock.patch('os.path.getmtime', mock.Mock(return_value=1500763154.0))
    def test_calling_refresh_cert_script_with_failing_old_domain(self):
        with ignore_signal(pre_save, post_save):
            self.instance.domains = [TEST_DOMAIN]
            self.instance.save()

            self.hosting.domains = [TEST_DOMAIN]
            self.hosting.ssl_status = Hosting.SSL_STATUSES.ON
            self.hosting.save()

        with mock.patch('os.path.exists', mock.Mock(return_value=True)):
            with mock.patch('os.listdir', mock.Mock(return_value=[TEST_DOMAIN])):
                HostingRefreshSecureCustomDomainCertTask.delay()
        set_current_instance(self.instance)
        self.hosting.refresh_from_db()
        self.assertEqual(self.hosting.ssl_status, Hosting.SSL_STATUSES.INVALID_DOMAIN)

    @mock.patch('subprocess.check_output')
    def test_calling_refresh_cert_script_with_dead_instance(self, subprocess_mock):
        with mock.patch('os.path.exists', mock.Mock(return_value=True)):
            with mock.patch('os.listdir', mock.Mock(return_value=[TEST_DOMAIN])):
                HostingRefreshSecureCustomDomainCertTask.delay()
        self.assertEqual(subprocess_mock.call_args[0][0], [REMOVE_SSL_CERT_SCRIPT, TEST_DOMAIN])
