import datetime
from decimal import Decimal
from unittest import mock

import stripe
from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from django_dynamic_fixture import G
from munch import Munch
from psycopg2.extras import DateRange
from rest_framework import status
from rest_framework.test import APITestCase

from apps.admins.models import Admin
from apps.billing.models import Coupon, Event, Invoice, InvoiceItem, PricingPlan, Profile, Subscription
from apps.billing.views import COUPON_DOESNT_EXIST, INSTANCE_DOESNT_EXIST
from apps.core.tests.mixins import CleanupTestCaseMixin
from apps.instances.models import Instance


class TestDiscountsViewSet(CleanupTestCaseMixin, APITestCase):
    def setUp(self):
        self.url = reverse('v1:discount-list')
        self.admin = G(Admin, email='john@doe.com')
        self.apikey = self.admin.key
        self.instance = G(Instance, name='testinstance')
        self.admin.add_to_instance(self.instance)
        redeem_by = datetime.datetime.strptime('2020-11-12', "%Y-%m-%d").date()
        self.coupon = G(Coupon, redeem_by=redeem_by, name='test')

    def test_getting_discounts_is_successful(self):
        self.coupon.redeem(instance=self.instance, customer=self.admin)
        response = self.client.get(self.url, HTTP_X_API_KEY=self.apikey)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(response.data['objects'][0]['links']['self'])

    def test_admin_see_only_his_discounts(self):
        another_admin = G(Admin)
        another_admin.add_to_instance(self.instance)
        discount = self.coupon.redeem(instance=self.instance, customer=another_admin)
        response = self.client.get(self.url, HTTP_X_API_KEY=self.apikey)
        self.assertNotContains(response, discount.coupon.name)

    def test_admin_see_only_details_of_his_discount(self):
        another_admin = G(Admin)
        another_admin.add_to_instance(self.instance)
        discount = self.coupon.redeem(instance=self.instance, customer=another_admin)
        url = reverse('v1:discount-detail', args=(discount.id,))
        response = self.client.get(url, HTTP_X_API_KEY=self.apikey)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_getting_discounts_returns_discounts(self):
        self.coupon.redeem(instance=self.instance, customer=self.admin)
        response = self.client.get(self.url, HTTP_X_API_KEY=self.apikey)
        self.assertContains(response, self.coupon.name)

    def test_redeeming_coupon(self):
        data = {
            "instance": self.instance.id,
            "coupon": self.coupon.name
        }
        response = self.client.post(self.url, data=data, HTTP_X_API_KEY=self.apikey)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_redeeming_coupon_using_instance_name(self):
        data = {
            "instance": self.instance.name,
            "coupon": self.coupon.name
        }
        response = self.client.post(self.url, data=data, HTTP_X_API_KEY=self.apikey)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_redeeming_coupon_twice(self):
        data = {
            "instance": self.instance.id,
            "coupon": self.coupon.name
        }
        self.client.post(self.url, data=data, HTTP_X_API_KEY=self.apikey)

        response = self.client.post(self.url, data=data, HTTP_X_API_KEY=self.apikey)
        self.assertEqual(response.data,
                         {'__all__': ['Discount with this Instance, Coupon and Customer already exists.']})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_redeeming_coupon_with_nonexistent_instance(self):
        data = {
            "instance": 1337,
            "coupon": self.coupon.name
        }
        self.client.post(self.url, data=data, HTTP_X_API_KEY=self.apikey)

        response = self.client.post(self.url, data=data, HTTP_X_API_KEY=self.apikey)
        self.assertEqual(response.data,
                         INSTANCE_DOESNT_EXIST)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_redeeming_coupon_with_nonexistent_coupon(self):
        data = {
            "instance": self.instance.id,
            "coupon": "idontexist"
        }
        self.client.post(self.url, data=data, HTTP_X_API_KEY=self.apikey)

        response = self.client.post(self.url, data=data, HTTP_X_API_KEY=self.apikey)
        self.assertEqual(response.data,
                         COUPON_DOESNT_EXIST)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class TestCouponsViewSet(CleanupTestCaseMixin, APITestCase):
    def setUp(self):
        self.url = reverse('v1:coupon-list')
        self.admin = G(Admin, email='john@doe.com', is_staff=True)
        self.apikey = self.admin.key
        self.client.defaults['HTTP_X_API_KEY'] = self.apikey

    def test_creating_coupons(self):
        data = {
            "name": "test",
            "amount_off": 10.0,
            "percent_off": 0,
            "currency": "usd",
            "duration": 1,
            "redeem_by": "2020-11-11"
        }

        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(Coupon.objects.exists())

    def test_creating_coupons_with_uppercase_currency(self):
        data = {
            "name": "test",
            "amount_off": 10.0,
            "percent_off": 0,
            "currency": "USD",
            "duration": 1,
            "redeem_by": "2020-11-11"
        }

        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(Coupon.objects.exists())

    def test_creating_coupons_with_invalid_duration(self):
        data = {
            "name": "test",
            "amount_off": 10.0,
            "percent_off": 0,
            "currency": "usd",
            "duration": 0,
            "redeem_by": "2020-11-11"
        }

        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn(b'duration', response.content)

    def test_creating_coupons_without_percent_off(self):
        data = {
            "name": "test",
            "amount_off": 10.0,
            "currency": "usd",
            "duration": 1,
            "redeem_by": "2020-11-11"
        }

        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_creating_coupons_without_amount_off(self):
        data = {
            "name": "test",
            "currency": "usd",
            "duration": 1,
            "percent_off": 15,
            "redeem_by": "2020-11-11"
        }

        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_creating_coupons_with_both_amount_off_and_percent_off(self):
        data_with_zeros = {
            "name": "test",
            "currency": "usd",
            "duration": 1,
            "percent_off": 0,
            "amount_off": 0.0,
            "redeem_by": "2020-11-11"
        }

        response = self.client.post(self.url, data_with_zeros)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        data_with_non_zeros = {
            "name": "test",
            "currency": "usd",
            "duration": 1,
            "percent_off": 40,
            "amount_off": 30.0,
            "redeem_by": "2020-11-11"
        }

        response = self.client.post(self.url, data_with_non_zeros)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_not_authorized_users_cannot_view_coupons(self):
        del self.client.defaults['HTTP_X_API_KEY']
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_not_staff_admins_cannot_view_coupons(self):
        del self.client.defaults['HTTP_X_API_KEY']
        admin = G(Admin, email='john2@doe.com')
        apikey = admin.key
        response = self.client.get(self.url, HTTP_X_API_KEY=apikey)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_viewing_coupons(self):
        # create a coupon
        coupon_name = 'imacoupon'
        redeem_by = datetime.datetime.strptime('2020-11-12', "%Y-%m-%d").date()
        G(Coupon, name=coupon_name, redeem_by=redeem_by)

        response = self.client.get(self.url)
        self.assertContains(response, coupon_name)
        self.assertIsNotNone(response.data['objects'][0]['links']['self'])


class TestInvoicesViewSet(CleanupTestCaseMixin, APITestCase):
    url = reverse('v1:invoice-list')

    def setUp(self):
        self.admin = G(Admin, email='john@doe.com')
        self.apikey = self.admin.key
        self.invoice = G(Invoice, admin=self.admin, status=Invoice.STATUS_CHOICES.PAYMENT_SCHEDULED)
        self.invoice_item = G(InvoiceItem, invoice=self.invoice, quantity=1000000)

        self.client.defaults['HTTP_X_API_KEY'] = self.apikey

    def test_forbidden_requests(self):
        detail_url = reverse('v1:invoice-detail', args=(self.invoice.pk,))
        requests = {
            self.url: ['post'],
            detail_url: ['post', 'delete', 'patch', 'put'],
        }

        for url, methods in requests.items():
            for method in methods:
                method = getattr(self.client, method)
                response = method(url)
                self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_pdf_custom_action(self):
        url = reverse('v1:invoice-pdf', args=(self.invoice.pk,))
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response['Content-Type'], 'application/pdf')

    def test_getting_invoices(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(response.data['objects'][0]['links']['self'])

    def test_retrieving_particular_invoice(self):
        url = reverse('v1:invoice-detail', args=(self.invoice.pk,))
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_retrieving_invalid_invoice(self):
        invoice = G(Invoice, admin=self.admin, status=Invoice.STATUS_CHOICES.NEW)
        url = reverse('v1:invoice-detail', args=(invoice.pk,))
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class TestInvoicesRetryViewSet(CleanupTestCaseMixin, APITestCase):
    def setUp(self):
        self.admin = G(Admin, email='john@doe.com')
        self.apikey = self.admin.key
        self.client.defaults['HTTP_X_API_KEY'] = self.apikey

    def create_invoice(self, status=Invoice.STATUS_CHOICES.PAYMENT_FAILED):
        return G(Invoice, admin=self.admin, status=status,
                 plan_fee=Decimal('3.50'), overage_amount=Decimal('16.49'))

    @mock.patch('apps.billing.models.Invoice.create_charge', return_value=Munch(id='dummy'))
    def test_retry_payment_charges_for_correct_invoice_status(self, create_charge_mock):
        invoice = self.create_invoice()
        url = reverse('v1:invoice-retry-payment', args=(invoice.id,))

        self.assertFalse(create_charge_mock.called)
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(create_charge_mock.called)

        self.assertTrue(Invoice.objects.filter(pk=invoice.pk,
                                               external_id='dummy',
                                               status=Invoice.STATUS_CHOICES.PAYMENT_SCHEDULED).exists())

    @mock.patch('apps.billing.models.Invoice.create_charge', return_value=Munch(id='dummy'))
    def test_retry_payment_for_invoice_with_incorrect_status(self, create_charge_mock):
        invoice = self.create_invoice(Invoice.STATUS_CHOICES.PAYMENT_SCHEDULED)
        self.assertIsNone(self.client.get(reverse('v1:billing-profile')).data['failed_invoice'])

        url = reverse('v1:invoice-retry-payment', args=(invoice.id,))

        self.client.post(url)
        self.assertFalse(create_charge_mock.called)

    def test_retry_payment_failing(self):
        invoice = self.create_invoice()
        self.assertIsNotNone(self.client.get(reverse('v1:billing-profile')).data['failed_invoice'])

        url = reverse('v1:invoice-retry-payment', args=(invoice.id,))
        exc_message = 'ohmygawdness'
        fake_exc = stripe.CardError(message=exc_message, param=None, code=None)

        with mock.patch('apps.billing.models.Invoice.create_charge', side_effect=fake_exc) as create_charge_mock:
            response = self.client.post(url)
            self.assertTrue(create_charge_mock.called)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue(response.data['detail'].endswith(exc_message))


@mock.patch('apps.billing.views.CardViewSet.get_resource')
class TestCardViewSet(CleanupTestCaseMixin, APITestCase):
    url = reverse('v1:billing-card')

    def setUp(self):
        self.admin = G(Admin, email='john@doe.com')
        self.apikey = self.admin.key
        self.client.defaults['HTTP_X_API_KEY'] = self.apikey

    @mock.patch('apps.billing.views.CardViewSet.get_customer')
    def test_create(self, get_customer_mock, get_resource_mock):
        get_resource_mock.return_value = get_resource_mock
        get_resource_mock.create.return_value = stripe.Card(id='dummy')

        response = self.client.post(self.url, data={'token': 'dummy-token'})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(get_resource_mock.called)
        self.assertTrue(get_resource_mock.create.called)
        get_resource_mock.create.assert_called_once_with(card='dummy-token')

    @mock.patch('apps.billing.views.StripeCardSerializer.data', mock.MagicMock())
    def test_update(self, get_resource_mock):
        card_mock = mock.Mock(id='dummy')
        response_mock = mock.Mock(data=[card_mock])
        get_resource_mock.return_value = get_resource_mock
        get_resource_mock.all.return_value = response_mock

        response = self.client.put(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(get_resource_mock.called)
        self.assertTrue(get_resource_mock.all.called)
        self.assertTrue(card_mock.save.called)
        get_resource_mock.all.assert_called_once_with()

    def test_retrieve(self, get_resource_mock):
        response_mock = mock.Mock(data=[{'id': 'dummy'}])
        get_resource_mock.return_value = get_resource_mock
        get_resource_mock.all.return_value = response_mock

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(get_resource_mock.called)
        self.assertTrue(get_resource_mock.all.called)
        get_resource_mock.all.assert_called_once_with()

    def test_empty_retrieve(self, get_resource_mock):
        get_resource_mock.return_value = get_resource_mock
        get_resource_mock.all.side_effect = KeyError

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertTrue(get_resource_mock.called)
        self.assertTrue(get_resource_mock.all.called)
        get_resource_mock.all.assert_called_once_with()

    def test_destroy(self, get_resource_mock):
        card_mock = mock.Mock()
        response_mock = mock.Mock(data=[card_mock])
        get_resource_mock.return_value = get_resource_mock
        get_resource_mock.all.return_value = response_mock

        response = self.client.delete(self.url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertTrue(get_resource_mock.called)
        self.assertTrue(get_resource_mock.all.called)
        self.assertTrue(card_mock.delete.called)
        get_resource_mock.all.assert_called_once_with()
        card_mock.delete.assert_called_once_with()


class TestEventViewSet(CleanupTestCaseMixin, APITestCase):
    def setUp(self):
        self.url = reverse('v1:event-list')
        self.event_data = {
            'id': 'evt_15mkjHLT2jyhELX3DQTJU0sx',
            'created': 1427890435,
            'livemode': False,
            'type': 'customer.created',
            'data': {'x': 1, 'y': 2}
        }

    def test_invalid_methods(self):
        for method_name in ['get', 'delete', 'put', 'patch']:
            method = getattr(self.client, method_name)
            response = method(self.url)
            self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    @mock.patch('stripe.Event.retrieve')
    def test_create(self, retrieve_mock):
        retrieve_mock.return_value = self.event_data

        self.assertEqual(Event.objects.count(), 0)
        response = self.client.post(self.url, self.event_data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(Event.objects.count(), 1)
        self.assertTrue(retrieve_mock.called)

        event = Event.objects.get(external_id=self.event_data['id'])
        self.assertTrue(event.valid)
        self.assertEqual(event.type, self.event_data['type'])
        self.assertEqual(event.livemode, self.event_data['livemode'])
        self.assertEqual(event.message, self.event_data)
        self.assertIsNotNone(event.created_at)

    @mock.patch('stripe.Event.retrieve')
    @mock.patch('apps.billing.views.logger.error')
    def test_duplicated_event(self, error_mock, retrieve_mock):
        retrieve_mock.return_value = self.event_data

        self.assertEqual(Event.objects.count(), 0)
        response = self.client.post(self.url, self.event_data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(error_mock.called)

        self.assertEqual(Event.objects.count(), 1)
        response = self.client.post(self.url, self.event_data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(error_mock.called)
        self.assertEqual(Event.objects.count(), 1)

    @mock.patch('stripe.Event.retrieve')
    def test_invalid_event(self, retrieve_mock):
        retrieve_mock.return_value = {
            'id': 'evt_15mkjHLT2jyhELX3DQTJU0sx',
            'created': 1427890435,
            'livemode': True,
            'type': 'customer.created',
            'data': {'a': 1, 'b': 2}
        }

        self.assertEqual(Event.objects.count(), 0)
        response = self.client.post(self.url, self.event_data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(Event.objects.count(), 1)
        self.assertTrue(retrieve_mock.called)
        event = Event.objects.get(external_id=self.event_data['id'])
        self.assertFalse(event.valid)


class TestProfileViewSet(CleanupTestCaseMixin, APITestCase):
    url = reverse('v1:billing-profile')

    def setUp(self):
        self.admin = G(Admin, email='john@doe.com', is_active=True)
        self.apikey = self.admin.key
        self.client.defaults['HTTP_X_API_KEY'] = self.apikey
        PricingPlan.objects.update(adjustable_limits=True)

    @override_settings(POST_TRANSACTION_SUCCESS_EAGER=True)
    def test_limit_is_rechecked_on_update(self):
        self.assertFalse(Profile.is_hard_limit_reached(self.admin.id))
        G(Invoice, admin=self.admin, period=Invoice.current_period(), overage_amount=100)
        self.client.patch(self.url, {'hard_limit': '10'})
        self.assertTrue(Profile.is_hard_limit_reached(self.admin.id))

        self.client.patch(self.url, {'hard_limit': '100'})
        self.assertFalse(Profile.is_hard_limit_reached(self.admin.id))

    def test_negative_soft_limit(self):
        response = self.client.put(self.url, {'soft_limit': '-4'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue('soft_limit' in response.data)

    def test_negative_hard_limit(self):
        response = self.client.put(self.url, {'hard_limit': '-4'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue('hard_limit' in response.data)

    def test_invalid_data(self):
        response = self.client.put(self.url, {'soft_limit': '100', 'hard_limit': '10'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue('soft_limit' in response.data)

    @override_settings(POST_TRANSACTION_SUCCESS_EAGER=True)
    def assert_profile_status(self, status):
        Profile.invalidate_billing_status(self.admin.id)
        response = self.client.get(self.url)
        self.assertEqual(response.data['status'], status)

    def test_billing_statuses(self):
        self.assert_profile_status('ok')

        with mock.patch('apps.billing.permissions.Profile.has_active_subscription', return_value=False):
            self.assert_profile_status('no_active_subscription')
        with mock.patch('apps.billing.permissions.Profile.is_hard_limit_reached', return_value=True):
            self.assert_profile_status('free_limits_exceeded')
        with mock.patch('apps.billing.permissions.Profile.has_overdue_invoices', return_value=True):
            self.assert_profile_status('overdue_invoices')


class TestSubscriptionProfileViewSet(CleanupTestCaseMixin, APITestCase):
    url = reverse('v1:billing-profile')

    def setUp(self):
        self.admin = G(Admin, email='john@doe.com', is_active=True)
        self.apikey = self.admin.key
        self.client.defaults['HTTP_X_API_KEY'] = self.apikey

    def test_expired_subscription(self):
        today = timezone.now().date()
        self.assertEqual(Subscription.objects.filter(admin_id=self.admin.pk).update(
            range=DateRange(today, today)), 1)
        response = self.client.get(self.url)
        self.assertIsNone(response.data['subscription'])

    def test_has_active_subscription(self):
        response = self.client.get(self.url)
        self.assertIsNotNone(response.data['subscription'])


class TestPricingPlanViewSet(APITestCase):
    def setUp(self):
        self.admin = G(Admin, email='john@doe.com')
        self.apikey = self.admin.key
        self.client.defaults['HTTP_X_API_KEY'] = self.apikey

    def test_list(self):
        url = reverse('v1:plan-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_detail(self):
        plan = PricingPlan.objects.available().first()
        url = reverse('v1:plan-detail', args=(plan.name,))
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(response.data['links']['self'])


class TestPricingPlanSubscribeViewSet(APITestCase):
    def setUp(self):
        self.admin = G(Admin, email='john@doe.com')
        self.apikey = self.admin.key
        self.client.defaults['HTTP_X_API_KEY'] = self.apikey
        self.plan = PricingPlan.objects.available().first()
        self.url = reverse('v1:plan-subscribe', args=(self.plan.name,))
        self.commitment = {key: value[0] for key, value in self.plan.options.items()}

    @mock.patch('apps.billing.models.Invoice.create_charge', return_value=Munch(id='dummy'))
    def test_subscribing_for_the_first_time_charges_me(self, create_charge_mock):
        # prepare subscription: start_date in the past;
        today = datetime.date.today()
        last_subscription = Subscription.objects.active_for_admin(admin_id=self.admin.id).get()
        last_subscription.range = DateRange(today - datetime.timedelta(days=5), None)
        last_subscription.save()

        self.assertFalse(create_charge_mock.called)
        response = self.client.post(self.url, {'commitment': self.commitment})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(create_charge_mock.called)

        plan_fee = self.plan.get_plan_fee(self.commitment, today).quantize(Decimal('.01'))
        self.assertTrue(Subscription.objects.filter(admin=self.admin, range__endswith=today).exists())

        self.assertTrue(Invoice.objects.filter(admin=self.admin,
                                               status=Invoice.STATUS_CHOICES.PAYMENT_SCHEDULED,
                                               plan_fee=plan_fee).exists())
        self.assertEqual(InvoiceItem.objects.count(), 1)

        current_sub = Subscription.objects.active_for_admin(self.admin).get()
        self.assertEqual(current_sub.start, today)
        self.assertIsNone(current_sub.end)
        self.assertEqual(current_sub.plan_id, self.plan.id)
        self.assertEqual(current_sub.commitment, self.commitment)
        self.assertEqual(current_sub.charged_until, Invoice.next_period())

    def test_subscription_is_not_created_when_charging_fails(self):
        self.assertEqual(Invoice.objects.count(), 0)
        self.assertEqual(Subscription.objects.count(), 1)

        exc_message = 'big nono'
        fake_exc = stripe.CardError(message=exc_message, param=None, code=None)
        with mock.patch('apps.billing.models.Invoice.create_charge', side_effect=fake_exc) as create_charge_mock:
            response = self.client.post(self.url, {'commitment': self.commitment})
            self.assertTrue(create_charge_mock.called)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Invoice.objects.count(), 0)
        self.assertEqual(Subscription.objects.count(), 1)
        self.assertTrue(response.data['detail'].endswith(exc_message))

    def test_subscribing_during_paid_plan_creates_new_sub(self):
        # Change current one to paid one without an end date
        current_sub = Subscription.objects.active_for_admin(self.admin).get()
        plan = PricingPlan.objects.filter(paid_plan=True).first()
        current_sub.plan = plan
        current_sub.range = DateRange(current_sub.start, None)
        current_sub.save()

        response = self.client.post(self.url, {'commitment': self.commitment})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        last_day_of_month = timezone.now() + datetime.timedelta(hours=settings.BILLING_GRACE_PERIOD_FOR_PLAN_CHANGING)
        last_day_of_month += relativedelta(months=+1, day=1)
        self.assertTrue(Subscription.objects.filter(pk=current_sub.pk, range__endswith=last_day_of_month).exists())
        self.assertTrue(Subscription.objects.exclude(pk=current_sub.pk).filter(range__startswith=last_day_of_month,
                                                                               plan=self.plan).exists())

    def test_subscribing_during_paid_plan_extends_last_sub(self):
        # Change current one to paid one without an end date
        current_sub = Subscription.objects.active_for_admin(self.admin).get()
        plan = PricingPlan.objects.filter(paid_plan=True).first()
        current_sub.plan = plan
        current_sub.commitment = self.commitment
        current_sub.save()

        response = self.client.post(self.url, {'commitment': self.commitment})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(Subscription.objects.filter(pk=current_sub.pk,
                                                    range__contains=datetime.date.max).exists())
        self.assertEqual(Subscription.objects.count(), 1)


class TestSubscriptionListViewSet(APITestCase):
    def setUp(self):
        self.admin = G(Admin, email='john@doe.com')
        self.apikey = self.admin.key
        self.client.defaults['HTTP_X_API_KEY'] = self.apikey
        self.url = reverse('v1:subscription-list')

    def test_listing_only_current_or_future_ones(self):
        plan = PricingPlan.objects.get_default()
        G(Subscription, admin=self.admin, range=DateRange(datetime.date(2010, 1, 1), datetime.date.today()), plan=plan)
        G(Subscription, admin=self.admin, range=DateRange(datetime.date(2050, 1, 1), None), plan=plan)

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['objects']), 2)  # include default sub

    def test_default_sub_has_end_date(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['objects']), 1)
        current_sub = response.data['objects'][0]
        self.assertIsNotNone(current_sub['end'])
        self.assertIsNotNone(current_sub['links'])


class TestSubscriptionDetailViewSet(APITestCase):
    def setUp(self):
        self.admin = G(Admin, email='john@doe.com')
        self.apikey = self.admin.key
        self.client.defaults['HTTP_X_API_KEY'] = self.apikey
        self.current_sub = Subscription.objects.active_for_admin(self.admin).get()
        self.url = reverse('v1:subscription-detail', args=(self.current_sub.id,))

    def test_detail(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class TestSubscriptionCancelViewSet(APITestCase):
    def setUp(self):
        self.admin = G(Admin, email='john@doe.com')
        self.apikey = self.admin.key
        self.client.defaults['HTTP_X_API_KEY'] = self.apikey

    def create_paid_subscription(self):
        # Change current one to paid one without an end date
        current_sub = Subscription.objects.active_for_admin(self.admin).get()
        plan = PricingPlan.objects.filter(paid_plan=True).first()
        current_sub.plan = plan
        current_sub.range = DateRange(current_sub.start, None)
        current_sub.save()
        return current_sub

    def test_cancelling_current_one_cuts_date(self):
        current_sub = self.create_paid_subscription()
        url = reverse('v1:subscription-cancel', args=(current_sub.id,))
        response = self.client.post(url)
        last_day_of_month = timezone.now() + datetime.timedelta(hours=settings.BILLING_GRACE_PERIOD_FOR_PLAN_CHANGING)
        last_day_of_month += relativedelta(months=+1, day=1)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(response.data['links']['self'])
        self.assertTrue(Subscription.objects.filter(pk=current_sub.pk, range__endswith=last_day_of_month).exists())

    def test_cancelling_future_sub_deletes_it(self):
        current_sub = self.create_paid_subscription()
        future_sub = G(Subscription, admin=self.admin, range=DateRange(datetime.date(2050, 1, 1), None),
                       plan=current_sub.plan)
        url = reverse('v1:subscription-cancel', args=(future_sub.id,))
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Subscription.objects.filter(pk=future_sub.pk).exists())
        self.assertTrue(Subscription.objects.filter(pk=current_sub.pk, range__endswith__isnull=True).exists())

    def test_cancelling_is_denied_for_unpaid_plan(self):
        current_sub = Subscription.objects.active_for_admin(self.admin).get()
        url = reverse('v1:subscription-cancel', args=(current_sub.id,))
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
