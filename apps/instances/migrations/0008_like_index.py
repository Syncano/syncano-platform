# -*- coding: utf-8 -*-
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('instances', '0007_add_instance_indicator__model'),
    ]

    operations = [
        migrations.RunSQL("""
CREATE INDEX instance_name_like ON instances_instance
USING BTREE (name varchar_pattern_ops);
        """)
    ]
