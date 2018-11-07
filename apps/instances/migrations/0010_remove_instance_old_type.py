# -*- coding: utf-8 -*-
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('instances', '0009_validators'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='instance',
            name='old_type',
        ),
    ]
