# -*- coding: utf-8 -*-
import jsonfield.fields
from django.db import migrations, models

import apps.core.fields


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0027_cleanup'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='pricingplan',
            name='verbose_name',
        ),
        migrations.AddField(
            model_name='pricingplan',
            name='available',
            field=models.BooleanField(default=True),
            preserve_default=True,
        ),
        migrations.RenameField(
            model_name='pricingplan',
            old_name='code_name',
            new_name='name'
        ),
        migrations.AlterField(
            model_name='pricingplan',
            name='name',
            field=apps.core.fields.StrippedSlugField(max_length=50, unique=True),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='pricingplan',
            name='pricing',
            field=jsonfield.fields.JSONField(default=''),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='subscription',
            name='charged_until',
            field=models.DateTimeField(null=True, blank=True),
            preserve_default=True,
        ),
        migrations.RenameField(
            model_name='subscription',
            old_name='pricing_plan',
            new_name='plan',
        ),
    ]
