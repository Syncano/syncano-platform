# -*- coding: utf-8 -*-
# Generated by Django 1.9.8 on 2017-08-14 14:01
import django.db.models.deletion
import jsonfield.fields
from django.db import migrations, models

import apps.core.fields
import apps.sockets.models
from apps.core.backends.storage import default_storage


class Migration(migrations.Migration):

    dependencies = [
        ('sockets', '0013_alter_status_info'),
    ]

    operations = [
        migrations.CreateModel(
            name='SocketEnvironment',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('metadata', jsonfield.fields.JSONField(blank=True, default={})),
                ('description', models.TextField(blank=True, max_length=256)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('name', apps.core.fields.StrippedSlugField(max_length=64)),
                ('status', models.SmallIntegerField(choices=[(-1, 'error'), (0, 'processing'), (1, 'ok')], default=0)),
                ('status_info', jsonfield.fields.JSONField(default=None, null=True)),
                ('zip_file', models.FileField(blank=True, null=True, upload_to=apps.sockets.models.upload_custom_socketenvironment_file_to,
                                              storage=default_storage)),
                ('fs_file', models.FileField(blank=True, null=True, upload_to=apps.sockets.models.upload_custom_socketenvironment_file_to,
                                             storage=default_storage)),
                ('_is_live', apps.core.fields.LiveField(db_index=True, default=True)),
            ],
            options={
                'ordering': ('id',),
            },
        ),
        migrations.AddField(
            model_name='socket',
            name='environment',
            field=models.ForeignKey(default=None, null=True, on_delete=django.db.models.deletion.SET_NULL, to='sockets.SocketEnvironment'),
        ),
    ]
