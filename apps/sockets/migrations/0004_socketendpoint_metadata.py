# -*- coding: utf-8 -*-
# Generated by Django 1.9.8 on 2016-09-15 11:47
import jsonfield.fields
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('sockets', '0003_socket_url'),
    ]

    operations = [
        migrations.AddField(
            model_name='socketendpoint',
            name='metadata',
            field=jsonfield.fields.JSONField(blank=True, default={}),
        ),
    ]
