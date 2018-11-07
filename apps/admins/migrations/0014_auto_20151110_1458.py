# -*- coding: utf-8 -*-
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('admins', '0013_remove_adminsocialprofile_email'),
    ]

    operations = [
        migrations.AlterField(
            model_name='adminsocialprofile',
            name='backend',
            field=models.SmallIntegerField(choices=[(0, 'facebook'), (1, 'google-oauth2'), (2, 'github'), (3, 'linkedin')]),
        ),
    ]
