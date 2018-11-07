# -*- coding: utf-8 -*-
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('billing', '0038_cleanup_nulls_data'),
    ]

    operations = [
        migrations.AlterField(
            model_name='invoice',
            name='admin',
            field=models.ForeignKey(related_name='invoices', to='admins.Admin', on_delete=models.CASCADE),
        ),
        migrations.AlterField(
            model_name='transaction',
            name='admin',
            field=models.ForeignKey(related_name='transactions', to='admins.Admin', on_delete=models.CASCADE),
        ),
    ]
