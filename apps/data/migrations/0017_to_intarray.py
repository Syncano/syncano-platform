# -*- coding: utf-8 -*-
from django.db import migrations

SQL = """
CREATE FUNCTION to_intarray(TEXT)
  RETURNS INTEGER[] AS $$
SELECT $1 :: INTEGER[];
$$ LANGUAGE SQL IMMUTABLE;
"""


class Migration(migrations.Migration):
    dependencies = [
        ('data', '0016_estimate_fix'),
    ]

    operations = [
        migrations.RunSQL(SQL),
    ]
