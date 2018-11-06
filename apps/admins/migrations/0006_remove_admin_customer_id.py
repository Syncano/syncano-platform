# -*- coding: utf-8 -*-
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('admins', '0005_auto_20150318_1059'),
        ('billing', '0007_auto_20150403_1434'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='admin',
            name='customer_id',
        ),
    ]
