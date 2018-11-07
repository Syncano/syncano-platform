# -*- coding: utf-8 -*-
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('metrics', '0012_cleanup'),
    ]

    operations = [
        migrations.AlterField(
            model_name='dayaggregate',
            name='source',
            field=models.SmallIntegerField(choices=[(0, b'API Call'), (1, b'CodeBox Exec')]),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='houraggregate',
            name='source',
            field=models.SmallIntegerField(choices=[(0, b'API Call'), (1, b'CodeBox Exec')]),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='minuteaggregate',
            name='source',
            field=models.SmallIntegerField(choices=[(0, b'API Call'), (1, b'CodeBox Exec')]),
            preserve_default=True,
        ),
    ]
