from unittest import mock

from django.test import TestCase
from django.test.utils import override_settings
from django_dynamic_fixture import G
from stripe import StripeError

from apps.admins.models import Admin
from apps.billing.models import Profile
from apps.billing.tasks import create_stripe_customer, remove_stripe_customer
from apps.core.tests.mixins import CleanupTestCaseMixin


@override_settings(POST_TRANSACTION_SUCCESS_EAGER=True)
@mock.patch('apps.billing.tasks.stripe.Customer.create', return_value={'id': '1'})
class TestCreateStripeCustomerTask(CleanupTestCaseMixin, TestCase):

    def setUp(self):
        self.admin = G(Admin, email='john@doe.com')
        self.profile = self.admin.billing_profile
        self.task = create_stripe_customer

    @override_settings(TESTING=False)
    @mock.patch('apps.billing.tasks.create_stripe_customer.retry')
    def test_stripe_error(self, retry_mock, create_mock):
        create_mock.side_effect = StripeError
        retry_mock.return_value = StripeError

        self.assertFalse(create_mock.called)
        self.assertFalse(retry_mock.called)

        with self.assertRaises(StripeError):
            self.task(self.profile.pk)

        self.assertTrue(create_mock.called)
        self.assertTrue(retry_mock.called)

        profile = Profile.objects.get(pk=self.profile.pk)
        self.assertEquals(profile.customer_id, self.profile.customer_id)

    @override_settings(TESTING=False)
    def test_create_stripe_customer(self, create_mock):
        self.assertFalse(create_mock.called)
        self.task(self.profile.pk, email=self.profile.admin.email)
        self.assertTrue(create_mock.called)

        profile = Profile.objects.get(pk=self.profile.pk)
        self.assertEquals(profile.customer_id, '1')
        create_mock.assert_called_once_with(email=self.profile.admin.email)


@override_settings(POST_TRANSACTION_SUCCESS_EAGER=True)
@mock.patch('apps.billing.tasks.stripe.Customer.retrieve')
class TestRemoveStripeCustomerTask(CleanupTestCaseMixin, TestCase):

    def setUp(self):
        self.admin = G(Admin, email='john@doe.com')
        self.profile = self.admin.billing_profile
        self.profile.customer_id = 'dummy'
        self.profile.save()
        self.task = remove_stripe_customer

    @override_settings(TESTING=False)
    @mock.patch('apps.billing.tasks.remove_stripe_customer.retry')
    def test_stripe_error(self, retry_mock, retrieve_mock):
        retrieve_mock.side_effect = StripeError
        retry_mock.return_value = StripeError

        self.assertFalse(retrieve_mock.called)
        self.assertFalse(retry_mock.called)

        with self.assertRaises(StripeError):
            self.task(self.profile.pk, self.profile.customer_id)

        self.assertTrue(retrieve_mock.called)
        self.assertTrue(retry_mock.called)

        profile = Profile.objects.get(pk=self.profile.pk)
        self.assertEquals(profile.customer_id, self.profile.customer_id)

    @override_settings(TESTING=False)
    def tests_remove_stripe_customer(self, retrieve_mock):
        self.assertFalse(retrieve_mock.called)
        self.task(self.profile.pk, self.profile.customer_id)
        self.assertTrue(retrieve_mock.called)

        profile = Profile.objects.get(pk=self.profile.pk)
        self.assertEquals(profile.customer_id, '')
        retrieve_mock.assert_called_once_with(self.profile.customer_id)
