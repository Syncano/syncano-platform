# coding=UTF8
from django.test import TestCase
from django.utils.translation import ugettext_lazy

from apps.core.helpers import evaluate_promises


class TestHelpers(TestCase):
    def test_evaluate_promises(self):
        real_text = 'something lazy'
        lazy_text = ugettext_lazy(real_text)
        self.assertEqual(evaluate_promises(lazy_text), real_text)
        self.assertEqual(evaluate_promises({'key': ['something', lazy_text]}), {'key': ['something', real_text]})
