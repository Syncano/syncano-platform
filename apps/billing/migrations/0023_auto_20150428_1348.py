# -*- coding: utf-8 -*-
from django.db import migrations


def change_plan_to_linear(apps, schema_editor):
    PricingPlan = apps.get_model('billing', "PricingPlan")
    Subscription = apps.get_model('billing', "Subscription")
    try:
        linear_pricing_plan = PricingPlan.objects.get(code_name='LINEAR')
        Subscription.objects.update(pricing_plan=linear_pricing_plan)
    except PricingPlan.DoesNotExist:
        pass


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0022_auto_20150427_1501'),
    ]

    operations = [
        migrations.RunPython(change_plan_to_linear),
    ]
