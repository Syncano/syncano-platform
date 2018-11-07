# -*- coding: utf-8 -*-
from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0034_invoice_is_prorated'),
    ]

    operations = [
        migrations.AlterField(
            model_name='invoiceitem',
            name='price',
            field=models.DecimalField(default=Decimal('0'), max_digits=12, decimal_places=7),
            preserve_default=True,
        ),
    ]
