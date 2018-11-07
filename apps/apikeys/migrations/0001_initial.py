# -*- coding: utf-8 -*-
import django.core.validators
import django.utils.timezone
from django.db import migrations, models

import apps.core.fields
import apps.data.fields


class Migration(migrations.Migration):

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='ApiKey',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('permissions_updated', models.DateTimeField(auto_now_add=True)),
                ('date_joined', models.DateTimeField(default=django.utils.timezone.now, verbose_name='date joined')),
                ('description', models.TextField(blank=True, validators=[django.core.validators.MaxLengthValidator(256)])),
                ('options', apps.core.fields.DictionaryField(verbose_name='options', null=True, editable=False)),
                ('_is_live', apps.core.fields.LiveField(default=True)),
                ('key', apps.core.fields.LowercaseCharField(max_length=40)),
            ],
            options={
                'ordering': ('id',),
            },
            bases=(models.Model,),
        ),
        migrations.AlterUniqueTogether(
            name='apikey',
            unique_together=set([('key', '_is_live')]),
        ),
    ]
