# -*- coding: utf-8 -*-
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('channels', '0004_like_index'),
    ]

    operations = [
        migrations.AlterField(
            model_name='channel',
            name='description',
            field=models.TextField(max_length=256, blank=True),
            preserve_default=True,
        ),
    ]
