# -*- coding: utf-8 -*-
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('admins', '0003_merge'),
    ]

    operations = [
        migrations.AddField(
            model_name='admin',
            name='customer_id',
            field=models.CharField(help_text='Designates relation between our user and entity in external payment service (Stripe).', max_length=18, verbose_name='customer id', db_index=True, blank=True),
            preserve_default=True,
        ),
    ]
