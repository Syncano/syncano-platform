# -*- coding: utf-8 -*-
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('sockets', '0009_remove_obsolete_fields'),
        ('hosting', '0007_hostingfile_checksum'),
    ]

    operations = [
        migrations.AddField(
            model_name='hosting',
            name='socket',
            field=models.ForeignKey(blank=True, default=None, null=True, on_delete=django.db.models.deletion.CASCADE, to='sockets.Socket'),
        ),
    ]
