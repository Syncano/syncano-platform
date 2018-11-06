# -*- coding: utf-8 -*-
from django.db import migrations, models

import apps.core.fields


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='coupon',
            name='currency',
            field=apps.core.fields.LowercaseCharField(default='usd', max_length=3, choices=[('usd', 'USD')]),
            preserve_default=True,
        ),
    ]
