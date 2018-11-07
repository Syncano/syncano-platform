# -*- coding: utf-8 -*-
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0023_auto_20150428_1348'),
    ]

    operations = [
        migrations.AlterField(
            model_name='invoiceitem',
            name='instance_name',
            field=models.CharField(max_length=64),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='transaction',
            name='instance_name',
            field=models.CharField(max_length=64),
            preserve_default=True,
        ),
    ]
