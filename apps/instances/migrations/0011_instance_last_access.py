# -*- coding: utf-8 -*-
# Generated by Django 1.9.1 on 2016-01-13 07:50
import datetime

from django.db import migrations, models
from django.utils.timezone import utc

UPDATE_SQL = ("UPDATE instances_instance "
              "SET last_access = COALESCE("
                  "(SELECT timestamp"
                  " FROM metrics_houraggregate"
                  " WHERE instance_id = instances_instance.id"
                  " ORDER BY id DESC LIMIT 1),updated_at) "
               "WHERE _is_live = true;")

class Migration(migrations.Migration):

    dependencies = [
        ('instances', '0010_remove_instance_old_type'),
        ('metrics', '0014_source_to_char'),
    ]

    operations = [
        migrations.AddField(
            model_name='instance',
            name='last_access',
            field=models.DateTimeField(auto_now_add=True, default=datetime.datetime(2016, 1, 13, 7, 50, 44, 156704, tzinfo=utc)),
            preserve_default=False,
        ),
        migrations.RunSQL(UPDATE_SQL, reverse_sql=migrations.RunSQL.noop)
    ]
