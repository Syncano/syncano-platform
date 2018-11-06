# -*- coding: utf-8 -*-
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0013_auto_20150416_0932'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='profile',
            name='balance',
        ),
    ]
