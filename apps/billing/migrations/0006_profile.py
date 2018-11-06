# -*- coding: utf-8 -*-
from decimal import Decimal

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('admins', '0005_auto_20150318_1059'),
        ('billing', '0005_event'),
    ]

    operations = [
        migrations.CreateModel(
            name='Profile',
            fields=[
                ('admin', models.OneToOneField(related_name='billing', primary_key=True, serialize=False, to=settings.AUTH_USER_MODEL, on_delete=models.CASCADE)),
                ('customer_id', models.CharField(db_index=True, max_length=18, blank=True)),
                ('soft_limit', models.DecimalField(default=Decimal('0.00'), max_digits=12, decimal_places=2)),
                ('hard_limit', models.DecimalField(default=Decimal('0.00'), max_digits=12, decimal_places=2)),
                ('balance', models.DecimalField(default=Decimal('0.00'), max_digits=12, decimal_places=2)),
            ],
            options={
            },
            bases=(models.Model,),
        ),
    ]
