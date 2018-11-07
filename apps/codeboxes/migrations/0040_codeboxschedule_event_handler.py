# -*- coding: utf-8 -*-
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('codeboxes', '0039_path_unique_with_socket'),
    ]

    operations = [
        migrations.AddField(
            model_name='codeboxschedule',
            name='event_handler',
            field=models.TextField(default=None, null=True),
        ),
    ]
