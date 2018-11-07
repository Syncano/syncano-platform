# -*- coding: utf-8 -*-
from django.db import migrations, models


def cleanup_nulls(apps, schema_editor):
    Invoice = apps.get_model('billing', 'Invoice')
    Transaction = apps.get_model('billing', 'Transaction')
    models = (Invoice, Transaction)

    for model in models:
        model.objects.filter(admin__isnull=True).delete()


class Migration(migrations.Migration):
    dependencies = [
        ('billing', '0037_adminlimit_data'),
    ]

    operations = [
        migrations.RunPython(cleanup_nulls),
    ]
