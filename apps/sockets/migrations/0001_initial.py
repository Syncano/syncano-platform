# -*- coding: utf-8 -*-
import django.db.models.deletion
import jsonfield.fields
from django.db import migrations, models

import apps.core.fields
import apps.core.validators


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Socket',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('metadata', jsonfield.fields.JSONField(blank=True, default={})),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('name', apps.core.fields.StrippedSlugField(
                    max_length=64, allow_slash=True,
                    validators=[apps.core.validators.NotInValidator(values={'install'})])
                 ),
                ('endpoints', jsonfield.fields.JSONField()),
                ('dependencies', jsonfield.fields.JSONField(blank=True, default={})),
                ('status', models.SmallIntegerField(choices=[(-2, 'processing'), (-1, 'error'), (0, 'checking'), (1, 'ok'), (2, 'prompt')], default=-2)),
                ('status_info', models.TextField(blank=True)),
                ('_is_live', apps.core.fields.LiveField(default=True)),
            ],
            options={
                'ordering': ('id',),
            },
        ),
        migrations.CreateModel(
            name='SocketEndpoint',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', apps.core.fields.LowercaseCharField(max_length=64, unique=True)),
                ('calls', jsonfield.fields.JSONField()),
                ('socket', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='sockets.Socket')),
            ],
            options={
                'ordering': ('id',),
            },
        ),
        migrations.AlterUniqueTogether(
            name='socket',
            unique_together=set([('name', '_is_live')]),
        ),
    ]
