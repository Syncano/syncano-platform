# -*- coding: utf-8 -*-
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0010_auto_20150410_1255'),
    ]

    operations = [
        migrations.AlterField(
            model_name='invoice',
            name='amount',
            field=models.DecimalField(max_digits=15, decimal_places=5),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='invoiceitem',
            name='amount',
            field=models.DecimalField(max_digits=15, decimal_places=5),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='transaction',
            name='amount',
            field=models.DecimalField(max_digits=15, decimal_places=5),
            preserve_default=True,
        ),
    ]
