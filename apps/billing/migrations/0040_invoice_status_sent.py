# -*- coding: utf-8 -*-
from django.db import migrations, models


def mark_invoices_as_sent(apps, schema_editor):
    model = apps.get_model('billing', 'Invoice')
    model.objects.all().update(status_sent=True)


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0039_cleanup_nulls'),
    ]

    operations = [
        migrations.AddField(
            model_name='invoice',
            name='status_sent',
            field=models.BooleanField(default=False),
        ),
        migrations.AlterIndexTogether(
            name='invoice',
            index_together=set([('admin', 'status', 'due_date'), ('status_sent', 'id')]),
        ),
        migrations.RunPython(mark_invoices_as_sent),
    ]
