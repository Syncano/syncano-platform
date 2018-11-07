# -*- coding: utf-8 -*-
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('admins', '0014_auto_20151110_1458'),
    ]

    operations = [
        migrations.AlterField(
            model_name='adminsocialprofile',
            name='backend',
            field=models.SmallIntegerField(choices=[(0, 'facebook'), (1, 'google-oauth2'), (2, 'github'), (3, 'linkedin'), (4, 'twitter')]),
        ),
    ]
