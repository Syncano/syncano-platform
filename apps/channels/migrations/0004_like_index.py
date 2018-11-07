# -*- coding: utf-8 -*-
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('channels', '0003_channel_description'),
    ]

    operations = [
        migrations.RunSQL("""
CREATE INDEX channel_name_like ON channels_channel
USING BTREE (name varchar_pattern_ops);
        """)
    ]
