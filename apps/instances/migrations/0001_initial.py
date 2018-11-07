# -*- coding: utf-8 -*-
import re

import django.core.validators
from django.conf import settings
from django.db import migrations, models

import apps.core.fields
import apps.core.validators


class Migration(migrations.Migration):

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Instance',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('name', apps.core.fields.LowercaseCharField(max_length=64, validators=[django.core.validators.MinLengthValidator(5), django.core.validators.MaxLengthValidator(50), apps.core.validators.NotInValidator(values=('devcenter', 'support', 'sentry', 'admin', 'platform', 'redirect', 'media', 'signup', 'login', 'instance_subdomain', 'my_instance', 'instance_subdomain', 'myinstance', 'panel', 'account', 'noinstance', 'public', 'template1', 'status')), django.core.validators.RegexValidator(regex=re.compile('^[a-z][a-z0-9-_]*$'), message='Wrong characters used in name. Allowed characters are: alphanumerics (a-z, 0-9), hyphens and underscores. Name has to start with a letter.')])),
                ('description', models.TextField(blank=True, validators=[django.core.validators.MaxLengthValidator(100)])),
                ('old_type', models.BooleanField(default=False)),
                ('schema_name', models.CharField(max_length=62, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('_is_live', apps.core.fields.LiveField(default=True)),
                #('owner', models.ForeignKey(related_name='own_instances', to=settings.AUTH_USER_MODEL, on_delete=models.CASCADE)),
            ],
            options={
                'ordering': ('id',),
            },
            bases=(models.Model,),
        ),
        migrations.AlterUniqueTogether(
            name='instance',
            unique_together=set([('name', '_is_live')]),
        ),
    ]
