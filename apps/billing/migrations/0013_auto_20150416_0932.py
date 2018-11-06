# -*- coding: utf-8 -*-
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0012_auto_20150416_1034'),
    ]

    operations = [
        migrations.AlterField(
            model_name='invoice',
            name='external_id',
            field=models.CharField(max_length=50, blank=True),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='invoice',
            name='status',
            field=models.SmallIntegerField(default=0, choices=[(0, 'new'), (1, 'pending'), (2, b'scheduling failed'), (3, b'payment scheduled'), (4, b'payment failed'), (5, b'payment succeeded')]),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='invoiceitem',
            name='external_id',
            field=models.CharField(max_length=50, blank=True),
            preserve_default=True,
        ),
    ]
