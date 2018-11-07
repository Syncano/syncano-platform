# -*- coding: utf-8 -*-
from django.db import migrations

import apps.core.fields


class Migration(migrations.Migration):

    dependencies = [
        ('hosting', '0011_hosting_auth'),
    ]

    operations = [
        migrations.AddField(
            model_name='hosting',
            name='config',
            field=apps.core.fields.NullableJSONField(blank=True, default=None, null=True),
        ),
        migrations.AlterField(
            model_name='hosting',
            name='config',
            field=apps.core.fields.NullableJSONField(blank=True, default={}, null=True),
        ),
    ]
