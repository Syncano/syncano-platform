# -*- coding: utf-8 -*-
from django.db import migrations, models


def change_source_value_to_char(apps, schema_editor):
    DayAggregate = apps.get_model('metrics', "DayAggregate")
    HourAggregate = apps.get_model('metrics', "HourAggregate")
    MinuteAggregate = apps.get_model('metrics', "MinuteAggregate")
    models = (DayAggregate, HourAggregate, MinuteAggregate)

    for model in models:
        model.objects.filter(source=0).update(new_source='api')
        model.objects.filter(source=1).update(new_source='cbx')


class Migration(migrations.Migration):

    dependencies = [
        ('metrics', '0013_choices'),
    ]

    operations = [
        migrations.AddField(
            model_name='dayaggregate',
            name='new_source',
            field=models.CharField(default='a', max_length=3, choices=[('cbx', b'CodeBox Exec'), ('api', b'API Call')]),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='houraggregate',
            name='new_source',
            field=models.CharField(default='a', max_length=3, choices=[('cbx', b'CodeBox Exec'), ('api', b'API Call')]),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='minuteaggregate',
            name='new_source',
            field=models.CharField(default='a', max_length=3, choices=[('cbx', b'CodeBox Exec'), ('api', b'API Call')]),
            preserve_default=False,
        ),
        migrations.RunPython(change_source_value_to_char),
    ]
