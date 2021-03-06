# -*- coding: utf-8 -*-
# Generated by Django 1.9.7 on 2016-09-21 11:32
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('sockets', '0005_socket_config'),
        ('webhooks', '0013_acl'),
    ]

    operations = [
        migrations.AddField(
            model_name='webhook',
            name='socket',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE,
                                    to='sockets.Socket', default=None),
        ),
    ]
