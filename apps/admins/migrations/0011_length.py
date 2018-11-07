# -*- coding: utf-8 -*-
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('admins', '0010_role_as_fk'),
    ]

    operations = [
        migrations.AlterField(
            model_name='admin',
            name='first_name',
            field=models.CharField(max_length=64, verbose_name='first name', blank=True),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='admin',
            name='last_name',
            field=models.CharField(max_length=64, verbose_name='last name', blank=True),
            preserve_default=True,
        ),
    ]
