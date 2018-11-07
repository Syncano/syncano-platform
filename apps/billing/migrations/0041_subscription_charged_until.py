# -*- coding: utf-8 -*-
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0040_invoice_status_sent'),
    ]

    operations = [
        migrations.AddField(
            model_name='subscription',
            name='charged_until',
            field=models.DateField(null=True, blank=True),
        ),
        migrations.AlterField(
            model_name='subscription',
            name='end',
            field=models.DateField(db_index=True, null=True, blank=True),
        ),
        migrations.AlterField(
            model_name='subscription',
            name='start',
            field=models.DateField(db_index=True),
        ),
    ]
