# -*- coding: utf-8 -*-
# Generated by Django 1.9.8 on 2016-11-29 15:40
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('sockets', '0008_socket_zip_file'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='socket',
            name='dependencies',
        ),
        migrations.RemoveField(
            model_name='socket',
            name='endpoints',
        ),
    ]
