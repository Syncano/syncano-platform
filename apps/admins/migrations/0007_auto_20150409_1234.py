# -*- coding: utf-8 -*-
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('admins', '0006_remove_admin_customer_id'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='adminactivationkey',
            name='admin',
        ),
        migrations.DeleteModel(
            name='AdminActivationKey',
        ),
    ]
