# -*- coding: utf-8 -*-
import datetime

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0021_auto_20150424_1036'),
    ]

    operations = [
        migrations.AlterField(
            model_name='profile',
            name='soft_limit_reached',
            field=models.DateField(default=datetime.date(1970, 1, 1)),
            preserve_default=True,
        ),
    ]
