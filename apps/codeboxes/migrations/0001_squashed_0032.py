# -*- coding: utf-8 -*-
import datetime

import django.core.validators
import django.db.models.deletion
import jsonfield.fields
import timezone_utils.fields
from django.db import migrations, models
from django.utils.timezone import utc

import apps.core.fields


class Migration(migrations.Migration):
    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='CodeBox',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('description', models.TextField(blank=True, max_length=256)),
                ('label', models.CharField(blank=True, max_length=64)),
                ('runtime_name', models.CharField(choices=[
                    ('nodejs', 'nodejs'), ('python', 'python'), ('python_library_v4.2', 'python_library_v4.2'),
                    ('python_library_v5.0', 'python_library_v5.0'), ('php', 'php'), ('swift', 'swift'),
                    ('python3', 'python3'), ('golang', 'golang'), ('nodejs_library_v1.0', 'nodejs_library_v1.0'),
                    ('ruby', 'ruby'), ('nodejs_library_v0.4', 'nodejs_library_v0.4')
                ], max_length=40)),
                ('source', models.TextField(blank=True, max_length=3145728)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('config', jsonfield.fields.JSONField(blank=True, default={})),
                ('_is_live', apps.core.fields.LiveField(db_index=True, default=True)),
            ],
            options={
                'ordering': ('id',),
                'verbose_name': 'Script',
            },
        ),
        migrations.CreateModel(
            name='CodeBoxSchedule',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('description', models.TextField(blank=True, max_length=256)),
                ('label', models.CharField(blank=True, max_length=64)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('interval_sec', models.IntegerField(blank=True, default=None, null=True)),
                ('crontab', models.CharField(blank=True, max_length=40, null=True)),
                ('scheduled_next', models.DateTimeField(blank=True, db_index=True, null=True)),
                ('timezone', timezone_utils.fields.TimeZoneField(default='UTC', max_length=32)),
                ('codebox', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='schedules',
                                              to='codeboxes.CodeBox')),
            ],
            options={
                'ordering': ('id',),
                'verbose_name': 'Schedule',
            },
        ),
    ]
