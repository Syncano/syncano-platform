# -*- coding: utf-8 -*-
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0018_auto_20150421_1209'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='invoiceitem',
            name='external_id',
        ),
        migrations.RemoveField(
            model_name='invoiceitem',
            name='reference',
        ),
    ]
