# -*- coding: utf-8 -*-
import django.core.validators
from django.db import migrations, models

import apps.core.fields
import apps.data.fields


class Migration(migrations.Migration):

    dependencies = [
        ('data', '0001_squashed_0016'),
    ]

    operations = [
        migrations.CreateModel(
            name='DataObjectHighLevelApi',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('description', models.TextField(blank=True, validators=[django.core.validators.MaxLengthValidator(256)])),
                ('name', apps.core.fields.StrippedSlugField(unique=True, max_length=64)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('options', apps.core.fields.DictionaryField(verbose_name='options', null=True, editable=False)),
                ('_is_live', apps.core.fields.LiveField(default=True, db_index=True)),
                ('klass', models.ForeignKey(to='data.Klass', on_delete=models.CASCADE)),
            ],
            options={
                'ordering': ('id',),
            },
            bases=(models.Model,),
        ),
    ]
