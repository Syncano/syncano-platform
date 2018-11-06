# -*- coding: utf-8 -*-
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0014_remove_profile_balance'),
    ]

    operations = [
        migrations.AlterField(
            model_name='invoiceitem',
            name='source',
            field=models.SmallIntegerField(choices=[(0, b'API requests'), (1, 'Storage')]),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='transaction',
            name='source',
            field=models.SmallIntegerField(choices=[(0, b'API requests'), (1, 'Storage')]),
            preserve_default=True,
        ),
    ]
