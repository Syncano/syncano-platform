# -*- coding: utf-8 -*-
# Generated by Django 1.9.2 on 2016-03-14 08:29
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('instances', '0013_instance_database'),
    ]

    operations = [
        migrations.AddField(
            model_name='instance',
            name='storage_prefix',
            field=models.CharField(default=None, max_length=64, null=True),
        ),
    ]
