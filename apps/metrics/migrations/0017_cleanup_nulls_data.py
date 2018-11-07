# -*- coding: utf-8 -*-
from django.db import migrations, models


def cleanup_nulls(apps, schema_editor):
    DayAggregate = apps.get_model('metrics', 'DayAggregate')
    HourAggregate = apps.get_model('metrics', 'HourAggregate')
    MinuteAggregate = apps.get_model('metrics', 'MinuteAggregate')
    models = (DayAggregate, HourAggregate, MinuteAggregate)

    for model in models:
        model.objects.filter(admin__isnull=True).delete()


class Migration(migrations.Migration):
    dependencies = [
        ('metrics', '0016_ordering'),
    ]

    operations = [
        migrations.RunPython(cleanup_nulls),
    ]
