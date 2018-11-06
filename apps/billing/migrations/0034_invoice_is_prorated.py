# -*- coding: utf-8 -*-
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0033_strippedslug'),
    ]

    operations = [
        migrations.AddField(
            model_name='invoice',
            name='is_prorated',
            field=models.BooleanField(default=False),
            preserve_default=True,
        ),
    ]
