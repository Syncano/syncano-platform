# -*- coding: utf-8 -*-
import django.db.models.deletion
import jsonfield.fields
from django.db import migrations, models

import apps.push_notifications.fields


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ('users', '__first__'),
    ]

    operations = [
        migrations.CreateModel(
            name='GCMConfig',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('production_api_key', models.CharField(blank=True, max_length=40, null=True)),
                ('development_api_key', models.CharField(blank=True, max_length=40, null=True)),
            ],
            options={
                'verbose_name': 'GCM Config'
            },
        ),
        migrations.CreateModel(
            name='APNSConfig',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('production_certificate_name', models.CharField(blank=True, max_length=200, null=True)),
                ('production_certificate', models.BinaryField(blank=True, null=True)),
                ('production_bundle_identifier', models.CharField(blank=True, max_length=200, null=True)),
                ('production_expiration_date', models.DateTimeField(blank=True, null=True)),
                ('development_certificate_name', models.CharField(blank=True, max_length=200, null=True)),
                ('development_certificate', models.BinaryField(blank=True, null=True)),
                ('development_bundle_identifier', models.CharField(blank=True, max_length=200, null=True)),
                ('development_expiration_date', models.DateTimeField(blank=True, null=True)),
            ],
            options={
                'verbose_name': 'APNS Config'
            },
        ),
        migrations.CreateModel(
            name='GCMDevice',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('metadata', jsonfield.fields.JSONField(blank=True, default={})),
                ('label', models.CharField(blank=True, max_length=64)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE,
                                           to='users.User')),
                ('is_active', models.BooleanField(default=True)),
                ('device_id', apps.push_notifications.fields.HexIntegerField(blank=True, null=True)),
                ('registration_id', models.CharField(max_length=512, unique=True)),
            ],
            options={
                'ordering': ('id',),
                'verbose_name': 'GCM Device'
            },
        ),
        migrations.CreateModel(
            name='APNSDevice',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('metadata', jsonfield.fields.JSONField(blank=True, default={})),
                ('label', models.CharField(blank=True, max_length=64)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE,
                                           to='users.User')),
                ('is_active', models.BooleanField(default=True)),
                ('device_id', models.UUIDField(blank=True, null=True)),
                ('registration_id', models.CharField(max_length=64, unique=True)),
            ],
            options={
                'ordering': ('id',),
                'verbose_name': 'APNS Device'
            },
        ),
        migrations.CreateModel(
            name='GCMMessage',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('status', models.SmallIntegerField(
                    choices=[(0, 'scheduled'), (1, 'error'), (2, 'partially_delivered'), (3, 'delivered')], default=0)),
                ('content', jsonfield.fields.JSONField(default={})),
                ('result', jsonfield.fields.JSONField(default={})),
            ],
            options={
                'ordering': ('id',),
                'verbose_name': 'GCM Message',
            },
        ),
        migrations.CreateModel(
            name='APNSMessage',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('status', models.SmallIntegerField(
                    choices=[(0, 'scheduled'), (1, 'error'), (2, 'partially_delivered'), (3, 'delivered')], default=0)),
                ('content', jsonfield.fields.JSONField(default={})),
                ('result', jsonfield.fields.JSONField(default={})),
            ],
            options={
                'ordering': ('id',),
                'verbose_name': 'APNS Message'
            },
        ),
    ]
