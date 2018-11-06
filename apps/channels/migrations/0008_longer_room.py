# -*- coding: utf-8 -*-
from django.db import migrations

import apps.core.fields


class Migration(migrations.Migration):

    dependencies = [
        ('channels', '0007_default_channel'),
    ]

    operations = [
        migrations.AlterField(
            model_name='change',
            name='room',
            field=apps.core.fields.LowercaseCharField(max_length=128, null=True),
        ),
    ]
