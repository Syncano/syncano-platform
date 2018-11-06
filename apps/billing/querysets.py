from datetime import datetime

from django.conf import settings
from django.db.models import QuerySet
from django.utils import timezone


class PricingPlanQuerySet(QuerySet):
    def get_default(self):
        return self.get(name=settings.BILLING_DEFAULT_PLAN_NAME)

    def available(self):
        return self.filter(available=True)


class SubscriptionQuerySet(QuerySet):
    def active_for_admin(self, admin_id, now=None):
        now = now or timezone.now()
        if isinstance(now, datetime):
            now = now.date()
        return self.filter(admin=admin_id, range__contains=now)

    def get_overlapping(self, admin_id, range):
        obj = self.filter(admin=admin_id, range__overlap=range).order_by('-range').first()
        if obj is None:
            raise self.model.DoesNotExist(
                "%s matching query does not exist." %
                self.model._meta.object_name
            )
        return obj
