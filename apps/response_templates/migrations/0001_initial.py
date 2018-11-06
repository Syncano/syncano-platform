# -*- coding: utf-8 -*-
import jsonfield.fields
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='ResponseTemplate',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('name', models.CharField(unique=True, max_length=64)),
                ('content_type', models.CharField(max_length=255)),
                ('content', models.TextField(max_length=65536)),
                ('context', jsonfield.fields.JSONField(default={}, blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'ordering': ('id',),
                'verbose_name': 'ResponseTemplate',
            },
        ),
    ]
