# -*- coding: utf-8 -*-
import datetime

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0019_auto_20150422_1322'),
    ]

    operations = [
        migrations.AddField(
            model_name='profile',
            name='hard_limit_reached',
            field=models.DateField(default=datetime.date(1970, 1, 1)),
            preserve_default=False,
        ),
    ]
