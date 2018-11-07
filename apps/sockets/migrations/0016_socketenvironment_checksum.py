# -*- coding: utf-8 -*-
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('sockets', '0015_socket_zip_file_list'),
    ]

    operations = [
        migrations.AddField(
            model_name='socketenvironment',
            name='checksum',
            field=models.CharField(max_length=32, null=True),
        ),
    ]
