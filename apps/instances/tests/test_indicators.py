# coding=UTF8
from django.test import TestCase, override_settings
from django_dynamic_fixture import G

from apps.codeboxes.models import CodeBoxSchedule
from apps.core.tests.mixins import CleanupTestCaseMixin
from apps.instances.helpers import set_current_instance
from apps.instances.models import Instance, InstanceIndicator


@override_settings(POST_TRANSACTION_SUCCESS_EAGER=True)
class TestScheduleIndicator(CleanupTestCaseMixin, TestCase):

    def setUp(self):
        self.instance = G(Instance, name="testtest")
        set_current_instance(self.instance)

    def _get_indicator(self):
        return InstanceIndicator.objects.get(instance=self.instance, type=InstanceIndicator.TYPES.SCHEDULES_COUNT)

    def test_creating_new_schedule_increments_indicator(self):
        G(CodeBoxSchedule)
        indicator = self._get_indicator()
        self.assertEqual(indicator.value, 1)

    def test_deleting_new_schedule_decrements_indicator(self):
        for _ in range(5):
            G(CodeBoxSchedule)

        schedule = G(CodeBoxSchedule)
        indicator = self._get_indicator()
        self.assertEqual(indicator.value, 6)

        schedule.delete()

        indicator = self._get_indicator()
        self.assertEqual(indicator.value, 5)
