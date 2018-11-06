# -*- coding: utf-8 -*-
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('admins', '0009_role'),
    ]

    operations = [
        migrations.AlterField(
            model_name='admininstancerole',
            name='role',
            field=models.ForeignKey(related_name='instance_admins', to='admins.Role', on_delete=models.CASCADE),
            preserve_default=True,
        ),
    ]
