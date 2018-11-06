# -*- coding: utf-8 -*-
import re

import django.core.validators
import jsonfield.fields
from django.db import migrations, models

import apps.core.fields
import apps.core.validators


class Migration(migrations.Migration):

    dependencies = [
        ('instances', '0008_like_index'),
    ]

    operations = [
        migrations.AlterField(
            model_name='instance',
            name='description',
            field=models.TextField(max_length=256, blank=True),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='instance',
            name='metadata',
            field=jsonfield.fields.JSONField(default={}, blank=True),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='instance',
            name='name',
            field=apps.core.fields.StrippedSlugField(max_length=64, validators=[apps.core.validators.NotInValidator(values={'devcenter', 'support', 'sentry', 'admin', 'platform', 'redirect', 'media', 'signup', 'login', 'instance_subdomain', 'my_instance', 'instance_subdomain', 'myinstance', 'panel', 'account', 'noinstance', 'public', 'template1', 'status'}),
                 django.core.validators.RegexValidator(inverse_match=True, message='Double hyphens are reserved.', regex=re.compile('--'))]),
            preserve_default=True,
        ),
    ]
