# -*- coding: utf-8 -*-
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('apikeys', '0004_remove_apikey_permissions_updated'),
    ]

    operations = [
        migrations.AlterField(
            model_name='apikey',
            name='description',
            field=models.TextField(max_length=256, blank=True),
            preserve_default=True,
        ),
    ]
