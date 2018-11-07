# -*- coding: utf-8 -*-
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('admins', '0012_last_login'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='adminsocialprofile',
            name='email',
        ),
    ]
