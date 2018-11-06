# -*- coding: utf-8 -*-
from django.db import migrations

import apps.core.fields


class Migration(migrations.Migration):

    dependencies = [
        ('response_templates', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='responsetemplate',
            name='name',
            field=apps.core.fields.StrippedSlugField(unique=True, max_length=64),
        ),
    ]
