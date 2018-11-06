# -*- coding: utf-8 -*-
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('metrics', '0014_source_to_char'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='dayaggregate',
            name='source',
        ),
        migrations.RemoveField(
            model_name='houraggregate',
            name='source',
        ),
        migrations.RemoveField(
            model_name='minuteaggregate',
            name='source',
        ),
        migrations.RenameField(
            model_name='dayaggregate',
            old_name='new_source',
            new_name='source'
        ),
        migrations.RenameField(
            model_name='houraggregate',
            old_name='new_source',
            new_name='source'
        ),
        migrations.RenameField(
            model_name='minuteaggregate',
            old_name='new_source',
            new_name='source'
        ),
        migrations.AlterField(
            model_name='dayaggregate',
            name='source',
            field=models.CharField(max_length=3, choices=[('cbx', b'codebox execution'), ('api', b'api call')]),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='houraggregate',
            name='source',
            field=models.CharField(max_length=3, choices=[('cbx', b'codebox execution'), ('api', b'api call')]),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='minuteaggregate',
            name='source',
            field=models.CharField(max_length=3, choices=[('cbx', b'codebox execution'), ('api', b'api call')]),
            preserve_default=True,
        ),
    ]
