# -*- coding: utf-8 -*-
import datetime

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0020_profile_hard_limit_reached'),
    ]

    operations = [
        migrations.AlterField(
            model_name='profile',
            name='hard_limit_reached',
            field=models.DateField(default=datetime.date(1970, 1, 1)),
            preserve_default=True,
        ),
    ]
