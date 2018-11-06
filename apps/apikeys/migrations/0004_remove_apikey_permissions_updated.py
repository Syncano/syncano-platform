# -*- coding: utf-8 -*-
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('apikeys', '0003_created_at'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='apikey',
            name='permissions_updated',
        ),
    ]
