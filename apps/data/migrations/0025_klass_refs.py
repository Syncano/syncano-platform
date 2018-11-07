# -*- coding: utf-8 -*-
import jsonfield.fields
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('data', '0024_klass_visible'),
    ]

    operations = [
        migrations.AddField(
            model_name='klass',
            name='refs',
            field=jsonfield.fields.JSONField(default={}),
        ),
    ]
