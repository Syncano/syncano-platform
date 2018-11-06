# -*- coding: utf-8 -*-
# Generated by Django 1.9.4 on 2016-05-17 09:33
import django.contrib.postgres.fields
from django.db import migrations, models

import apps.core.fields


class Migration(migrations.Migration):

    dependencies = [
        ('data', '0017_to_intarray'),
    ]

    operations = [
        migrations.AddField(
            model_name='dataobject',
            name='_groups',
            field=django.contrib.postgres.fields.ArrayField(base_field=models.IntegerField(), blank=True, default=list, size=None),
        ),
        migrations.AddField(
            model_name='dataobject',
            name='_public',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='dataobject',
            name='_users',
            field=django.contrib.postgres.fields.ArrayField(base_field=models.IntegerField(), blank=True, default=list, size=None),
        ),
        migrations.AddField(
            model_name='dataobject',
            name='acl',
            field=apps.core.fields.NullableJSONField(blank=True, default=None, null=True),
        ),
        migrations.AlterField(
            model_name='dataobject',
            name='acl',
            field=apps.core.fields.NullableJSONField(blank=True, default={}, null=True),
        ),
        migrations.RunSQL("""
CREATE INDEX data_klass_acl_users ON data_dataobject
USING GIN (_users);

CREATE INDEX data_klass_acl_groups ON data_dataobject
USING GIN (_groups);

CREATE INDEX data_klass_acl_public ON data_dataobject
USING BTREE (_public) WHERE _public = true;
"""),
    ]
