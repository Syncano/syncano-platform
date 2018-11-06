# -*- coding: utf-8 -*-
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0016_auto_20150421_1355'),
    ]

    operations = [
        migrations.AddField(
            model_name='profile',
            name='soft_limit_reached',
            field=models.DateField(null=True, blank=True),
            preserve_default=True,
        ),
    ]
