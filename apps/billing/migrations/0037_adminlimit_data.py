# -*- coding: utf-8 -*-
from django.db import migrations


def create_limits(apps, schema_editor):
    Admin = apps.get_model('admins.Admin')
    AdminLimit = apps.get_model('billing.AdminLimit')
    for pk in Admin.objects.values_list('pk', flat=True):
        AdminLimit.objects.create(admin_id=pk)


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0036_adminlimit'),
    ]

    operations = [
        migrations.RunPython(create_limits),
    ]
