# -*- coding: utf-8 -*-
from django.db import migrations


def create_profiles(apps, schema_editor):
    Admin = apps.get_model('admins.Admin')
    Profile = apps.get_model('billing.Profile')
    for pk, customer_id in Admin.objects.values_list('pk', 'customer_id'):
        Profile.objects.create(admin_id=pk, customer_id=customer_id)


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0006_profile'),
    ]

    operations = [
        migrations.RunPython(create_profiles),
    ]
