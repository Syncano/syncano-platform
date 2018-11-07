# -*- coding: utf-8 -*-
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('metrics', '0015_after_trigger_source_rename'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='dayaggregate',
            options={'ordering': ('id',)},
        ),
        migrations.AlterModelOptions(
            name='houraggregate',
            options={'ordering': ('id',)},
        ),
        migrations.AlterModelOptions(
            name='minuteaggregate',
            options={'ordering': ('id',)},
        ),
    ]
