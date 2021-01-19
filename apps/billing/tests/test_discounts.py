import datetime

from django.core.exceptions import ValidationError
from django.test import TestCase
from django_dynamic_fixture import G

from apps.admins.models import Admin
from apps.instances.models import Instance

from ..models import Coupon


class TestDiscount(TestCase):

    def test_cannot_redeem_expired_coupon(self):
        redeem_by = datetime.datetime.strptime('2010-11-12', "%Y-%m-%d").date()
        coupon = G(Coupon, name='test',
                   duration=2, redeem_by=redeem_by)
        instance = G(Instance, name='testinstance')
        customer = G(Admin, email='john@doe.com')
        customer.add_to_instance(instance)
        self.assertRaises(ValidationError, coupon.redeem, instance=instance, customer=customer)

    def test_cannot_use_the_same_coupon_many_times_on_instance(self):
        redeem_by = datetime.datetime.strptime('2030-11-12', "%Y-%m-%d").date()
        coupon = G(Coupon, name='test',
                   duration=2, redeem_by=redeem_by)
        instance = G(Instance, name='testinstance')

        self.admin = G(Admin, email='john@doe.com')
        self.admin.add_to_instance(instance)

        coupon.redeem(instance=instance, customer=self.admin)

        self.assertRaises(ValidationError, coupon.redeem,
                          instance=instance, customer=self.admin)

    def test_cannot_use_the_same_coupon_on_not_owned_instance(self):
        coupon = G(Coupon, name='test',
                   duration=2, redeem_by='2011-10-10')
        self.admin = G(Admin, email='john@doe.com')
        instance = G(Instance, name='testinstance')
        self.assertRaises(ValidationError, coupon.redeem,
                          instance=instance, customer=self.admin)
