# -*- coding: utf-8 -*-
import jsonfield.fields
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('high_level', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='dataobjecthighlevelapi',
            name='query',
            field=jsonfield.fields.JSONField(default={}, blank=True),
            preserve_default=True,
        ),
    ]
