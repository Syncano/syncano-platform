# -*- coding: utf-8 -*-
import django.core.validators
import django.db.models.deletion
from django.db import migrations, models

import apps.core.fields


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ('codeboxes', '__first__'),
    ]

    operations = [
        migrations.CreateModel(
            name='Webhook',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('description', models.TextField(blank=True, max_length=256)),
                ('name', apps.core.fields.StrippedSlugField(max_length=64, unique=True)),
                ('public', models.BooleanField(default=False)),
                ('public_link', apps.core.fields.LowercaseCharField(max_length=40, unique=True)),
                ('codebox', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='codeboxes.CodeBox')),
            ],
            options={
                'ordering': ('id',),
                'verbose_name': 'Script Endpoint',
            },
        ),
        migrations.AlterIndexTogether(
            name='webhook',
            index_together=set([('public_link', 'public')]),
        ),

    ]
