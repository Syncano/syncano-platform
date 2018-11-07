# -*- coding: utf-8 -*-
import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('channels', '0002_length'),
    ]

    operations = [
        migrations.AddField(
            model_name='channel',
            name='description',
            field=models.TextField(blank=True, validators=[django.core.validators.MaxLengthValidator(256)]),
            preserve_default=True,
        ),
    ]
