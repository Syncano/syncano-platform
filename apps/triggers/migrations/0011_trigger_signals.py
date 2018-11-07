# -*- coding: utf-8 -*-
import django.contrib.postgres.fields
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('triggers', '0010_trigger_socket'),
    ]

    operations = [
        migrations.AlterField(
            model_name='trigger',
            name='signals',
            field=django.contrib.postgres.fields.ArrayField(base_field=models.TextField()),
        ),
    ]
