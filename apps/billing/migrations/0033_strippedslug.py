# -*- coding: utf-8 -*-
from django.db import migrations, models

import apps.core.fields


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0032_cleanup'),
    ]

    operations = [
        migrations.AlterField(
            model_name='pricingplan',
            name='name',
            field=apps.core.fields.StrippedSlugField(unique=True, max_length=64),
            preserve_default=True,
        ),
    ]
