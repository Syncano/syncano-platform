# -*- coding: utf-8 -*-
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('apikeys', '0002_apikey_instance'),
    ]

    operations = [
        migrations.RenameField(
            model_name='apikey',
            old_name='date_joined',
            new_name='created_at'
        ),
        migrations.AlterField(
            model_name='apikey',
            name='created_at',
            field=models.DateTimeField(auto_now_add=True),
            preserve_default=True,
        ),
    ]
