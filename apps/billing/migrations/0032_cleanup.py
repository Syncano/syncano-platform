# -*- coding: utf-8 -*-
from django.db import migrations


def change_source_value_to_char(apps, schema_editor):
    Transaction = apps.get_model('billing', "Transaction")
    InvoiceItem = apps.get_model('billing', "InvoiceItem")
    models = (Transaction, InvoiceItem)

    for model in models:
        model.objects.filter(source='0').update(source='api')
        model.objects.filter(source='1').update(source='cbx')

    Subscription = apps.get_model('billing', "Subscription")
    try:
        earliest_transaction = Transaction.objects.values_list('period', flat=True).earliest('period')
        Subscription.objects.update(start=earliest_transaction)
    except Transaction.DoesNotExist:
        pass


class Migration(migrations.Migration):
    dependencies = [
        ('billing', '0031_invoices'),
    ]

    operations = [
        migrations.RunPython(change_source_value_to_char),
    ]
