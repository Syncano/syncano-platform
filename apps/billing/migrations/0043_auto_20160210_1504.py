# -*- coding: utf-8 -*-
# Generated by Django 1.9.2 on 2016-02-10 15:04
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0042_charged_until_data'),
    ]

    operations = [
        migrations.AlterIndexTogether(
            name='profile',
            index_together=set([('admin', 'hard_limit_reached'), ('admin', 'soft_limit_reached')]),
        ),
    ]
