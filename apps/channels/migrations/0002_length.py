# -*- coding: utf-8 -*-
from django.db import migrations, models

import apps.core.fields


class Migration(migrations.Migration):

    dependencies = [
        ('channels', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='change',
            name='room',
            field=apps.core.fields.LowercaseCharField(max_length=64, null=True),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='channel',
            name='name',
            field=apps.core.fields.StrippedSlugField(max_length=64),
            preserve_default=True,
        ),
    ]
