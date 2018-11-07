# -*- coding: utf-8 -*-
from django.db import migrations
from django.utils import timezone


def change_plan_to_free(apps, schema_editor):
    PricingPlan = apps.get_model('billing', "PricingPlan")
    Subscription = apps.get_model('billing', "Subscription")
    Admin = apps.get_model('admins', "Admin")

    try:
        plan = PricingPlan.objects.get(name='free')
        Subscription.objects.update(plan=plan)
        today = timezone.now()
        for admin in Admin.objects.filter(subscriptions__isnull=True):
            Subscription.objects.create(plan=plan, admin=admin, start=today)
    except PricingPlan.DoesNotExist:
        pass


class Migration(migrations.Migration):
    dependencies = [
        ('billing', '0029_pricing'),
        ('admins', '0011_length'),
    ]

    operations = [
        migrations.RunPython(change_plan_to_free),
    ]
