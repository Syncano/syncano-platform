# -*- coding: utf-8 -*-
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0003_auto_20150306_0820'),
    ]

    operations = [
        migrations.AddField(
            model_name='subscription',
            name='charged_until',
            field=models.DateTimeField(null=True, blank=True),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='subscription',
            name='end',
            field=models.DateTimeField(null=True, blank=True),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='subscription',
            name='pricing_plan',
            field=models.ForeignKey(related_name='subscriptions', to='billing.PricingPlan', on_delete=models.CASCADE),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='subscription',
            name='start',
            field=models.DateTimeField(),
            preserve_default=True,
        ),
    ]
