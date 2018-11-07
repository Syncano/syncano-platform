# -*- coding: utf-8 -*-
from datetime import datetime

import jsonfield.fields
from django.db import migrations, models
from pytz import utc


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0028_plans'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='invoiceitem',
            options={'ordering': ('id',)},
        ),
        migrations.RemoveField(
            model_name='invoiceitem',
            name='amount',
        ),
        migrations.RemoveField(
            model_name='subscription',
            name='charged_until',
        ),
        migrations.RemoveField(
            model_name='transaction',
            name='amount',
        ),
        migrations.AddField(
            model_name='invoiceitem',
            name='price',
            field=models.DecimalField(default=0, max_digits=10, decimal_places=7),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='pricingplan',
            name='options',
            field=jsonfield.fields.JSONField(default={}),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='subscription',
            name='commitment',
            field=jsonfield.fields.JSONField(default={}, blank=True),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='invoice',
            name='amount',
            field=models.DecimalField(max_digits=15, decimal_places=7),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='invoice',
            name='period',
            field=models.DateField(db_index=True),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='invoiceitem',
            name='instance_id',
            field=models.IntegerField(db_index=True),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='invoiceitem',
            name='source',
            field=models.SmallIntegerField(choices=[(0, b'API Call'), (1, b'CodeBox Exec')]),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='transaction',
            name='source',
            field=models.SmallIntegerField(choices=[(0, b'API Call'), (1, b'CodeBox Exec')]),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='pricingplan',
            name='adjustable_limits',
            field=models.BooleanField(default=True),
            preserve_default=True,
        ),
        migrations.AlterIndexTogether(
            name='profile',
            index_together=set([('hard_limit', 'hard_limit_reached'), ('soft_limit', 'soft_limit_reached')]),
        ),
        migrations.AddField(
            model_name='invoice',
            name='due_date',
            field=models.DateField(default=datetime(2025, 1, 1, 0, 0, 0, 0, tzinfo=utc), db_index=True),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='pricingplan',
            name='paid_plan',
            field=models.BooleanField(default=True),
            preserve_default=True,
        ),
        migrations.RemoveField(
            model_name='transaction',
            name='type',
        ),
    ]
