# -*- coding: utf-8 -*-
from datetime import date

from dateutil.relativedelta import relativedelta
from django.db import migrations
from django.db.models import Case, F, Q, Value, When


def adjust_charged_until(apps, schema_editor):
    Subscription = apps.get_model('billing.Subscription')
    current_period = date.today() + relativedelta(day=1, months=+1)
    Subscription.objects.filter(plan__paid_plan=True).update(charged_until=Case(
        When(Q(end__gt=current_period) | Q(end__isnull=True), then=Value(current_period)),
        default=F('end')
    ))


class Migration(migrations.Migration):
    dependencies = [
        ('billing', '0041_subscription_charged_until'),
    ]

    operations = [
        migrations.RunPython(adjust_charged_until),
    ]
