# -*- coding: utf-8 -*-
from django.db import migrations, models


def fill_soft_limit_reached(apps, schema_editor):
    Profile = apps.get_model('billing.Profile')
    Profile.objects.filter(soft_limit_reached__isnull=True).update(soft_limit_reached='1970-01-01')


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0017_profile_soft_limit_reached'),
    ]

    operations = [
        migrations.RunPython(fill_soft_limit_reached),
        migrations.AlterField(
            model_name='profile',
            name='soft_limit_reached',
            field=models.DateField(),
            preserve_default=True,
        ),
    ]
