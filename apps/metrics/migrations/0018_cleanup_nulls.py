# -*- coding: utf-8 -*-
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('metrics', '0017_cleanup_nulls_data'),
    ]

    operations = [
        migrations.AlterField(
            model_name='dayaggregate',
            name='admin',
            field=models.ForeignKey(to='admins.Admin', on_delete=models.CASCADE),
        ),
        migrations.AlterField(
            model_name='houraggregate',
            name='admin',
            field=models.ForeignKey(to='admins.Admin', on_delete=models.CASCADE),
        ),
        migrations.AlterField(
            model_name='minuteaggregate',
            name='admin',
            field=models.ForeignKey(to='admins.Admin', on_delete=models.CASCADE),
        ),
    ]
