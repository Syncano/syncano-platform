# -*- coding: utf-8 -*-
from django.db import migrations

from apps.billing.tasks import create_stripe_customer


def create_stripe_customers(apps, schema_editor):
    Admin = apps.get_model('admins.Admin')
    for pk, email in Admin.objects.filter(customer_id='').values_list('pk', 'email'):
        create_stripe_customer(pk, email=email)


class Migration(migrations.Migration):

    dependencies = [
        ('admins', '0004_admin_customer_id'),
    ]

    operations = [
        migrations.RunPython(create_stripe_customers),
    ]
