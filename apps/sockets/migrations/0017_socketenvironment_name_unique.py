# -*- coding: utf-8 -*-
from django.db import migrations

import apps.core.fields


class Migration(migrations.Migration):

    dependencies = [
        ('sockets', '0016_socketenvironment_checksum'),
    ]

    operations = [
        migrations.AlterField(
            model_name='socketenvironment',
            name='_is_live',
            field=apps.core.fields.LiveField(default=True),
        ),
        migrations.AlterUniqueTogether(
            name='socketenvironment',
            unique_together=set([('name', '_is_live')]),
        ),
    ]
