# -*- coding: utf-8 -*-
from django.db import migrations


def create_channel(apps, schema_editor):
    Channel = apps.get_model('channels', 'Channel')
    Channel.objects.update_or_create({
        'type': 1,  # Channel.TYPES.SEPARATE_ROOMS
        'options': {'custom_publish': 'False'},
        'acl': {},
    }, name='eventlog')


class Migration(migrations.Migration):
    dependencies = [
        ('channels', '0008_longer_room'),
    ]

    operations = [
        migrations.RunPython(create_channel)
    ]
