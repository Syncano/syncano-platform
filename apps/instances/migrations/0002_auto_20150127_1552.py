# -*- coding: utf-8 -*-
import re

import django.core.validators
from django.conf import settings
from django.db import migrations, models

import apps.core.fields
import apps.core.validators


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('instances', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='instance',
            name='owner',
            field=models.ForeignKey(related_name='own_instances', default=None, to=settings.AUTH_USER_MODEL, on_delete=models.CASCADE),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name='instance',
            name='name',
            field=apps.core.fields.LowercaseCharField(max_length=64, validators=[django.core.validators.MinLengthValidator(5), django.core.validators.MaxLengthValidator(50), apps.core.validators.NotInValidator(values=('devcenter', 'support', 'sentry', 'admin', 'platform', 'redirect', 'media', 'signup', 'login', 'instance_subdomain', 'my_instance', 'instance_subdomain', 'myinstance', 'panel', 'account', 'noinstance', 'public', 'template1', 'status')), django.core.validators.RegexValidator(regex=re.compile('^[a-z][a-z0-9-_]*$'), message='Wrong characters used in name. Allowed characters are: alphanumerics (a-z, 0-9), hyphens and underscores. Name has to start with a letter.')]),
            preserve_default=True,
        ),
    ]
