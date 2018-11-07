# -*- coding: utf-8 -*-
import jsonfield
from django.db import migrations, models

import apps.core.fields
import apps.core.validators


class Migration(migrations.Migration):

    dependencies = [
        ('instances', '0003_auto_20150127_1712'),
    ]

    operations = [
        migrations.AddField(
            model_name='instance',
            name='metadata',
            field=jsonfield.JSONField(default={}, blank=True, validators=[apps.core.validators.validate_metadata]),
            preserve_default=True,
        ),
    ]
