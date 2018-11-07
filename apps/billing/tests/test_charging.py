from datetime import timedelta
from unittest import mock

from django.test import TestCase
from django.utils.timezone import now
from django_dynamic_fixture import G

from apps.metrics.helpers import floor_to_base
from apps.metrics.models import WorkLogEntry
from apps.metrics.tasks import AggregateHourTask

last_full_hour = floor_to_base(now(), base=timedelta(hours=1))


class ChargingTestCase(TestCase):
    @mock.patch('apps.billing.tasks.ChargeOneHour.run')
    def test_one_hour_is_charged_when_metrics_finish_calculating(self, mock_func):
        worklog = G(WorkLogEntry)
        AggregateHourTask.delay(worklog.id, (last_full_hour + timedelta(hours=1)).isoformat())
        mock_func.assert_called_with(last_full_hour.isoformat())
