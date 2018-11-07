# -*- coding: utf-8 -*-
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0026_instance_id'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='subscription',
            options={'ordering': ('id',)},
        ),
        migrations.RemoveField(
            model_name='pricingplan',
            name='available',
        ),
        migrations.AlterUniqueTogether(
            name='subscription',
            unique_together=set([]),
        ),
        migrations.RemoveField(
            model_name='subscription',
            name='charged_until',
        ),
    ]
