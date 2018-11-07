# -*- coding: utf-8 -*-
import jsonfield
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0004_auto_20150311_1654'),
    ]

    operations = [
        migrations.CreateModel(
            name='Event',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('external_id', models.CharField(unique=True, max_length=50)),
                ('type', models.CharField(max_length=50)),
                ('livemode', models.BooleanField(default=False)),
                ('message', jsonfield.JSONField(default={})),
                ('valid', models.NullBooleanField(default=None)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
            },
            bases=(models.Model,),
        ),
    ]
