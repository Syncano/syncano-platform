# -*- coding: utf-8 -*-
import re

import django.core.validators
from django.db import migrations, models

import apps.core.fields
import apps.core.validators


class Migration(migrations.Migration):

    dependencies = [
        ('instances', '0005_shorter_name'),
    ]

    operations = [
        migrations.AlterField(
            model_name='instance',
            name='name',
            field=apps.core.fields.StrippedSlugField(max_length=64, validators=[django.core.validators.MinLengthValidator(5), apps.core.validators.NotInValidator(values=('devcenter', 'support', 'sentry', 'admin', 'platform', 'redirect', 'media', 'signup', 'login', 'instance_subdomain', 'my_instance', 'instance_subdomain', 'myinstance', 'panel', 'account', 'noinstance', 'public', 'template1', 'status'))]),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='instance',
            name='schema_name',
            field=models.CharField(max_length=63, null=True),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='instance',
            name='description',
            field=models.TextField(blank=True, validators=[django.core.validators.MaxLengthValidator(256)]),
            preserve_default=True,
        ),
    ]
