# -*- coding: utf-8 -*-
from datetime import date

from django.db import migrations, models


def fix_transaction_period(apps, schema_editor):
    Transaction = apps.get_model('billing.Transaction')
    transactions = Transaction.objects.exclude(period__day=1).values('period').annotate(total=models.Count('pk'))
    for transaction in transactions:
        period = (transaction['period'] or date.today()).replace(day=1)
        Transaction.objects.filter(period=transaction['period']).update(period=period)


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0024_length'),
    ]

    operations = [
        migrations.RunPython(fix_transaction_period),
    ]
