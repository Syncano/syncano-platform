# -*- coding: utf-8 -*-
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('invitations', '0004_role_as_integer'),
    ]

    operations = [
        migrations.AlterField(
            model_name='invitation',
            name='role',
            field=models.ForeignKey(to='admins.Role', on_delete=models.CASCADE),
            preserve_default=True,
        ),
    ]
