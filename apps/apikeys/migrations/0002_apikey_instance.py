# -*- coding: utf-8 -*-
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('instances', '0004_instance_metadata'),
        ('apikeys', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='apikey',
            name='instance',
            field=models.ForeignKey(default=1, to='instances.Instance', on_delete=models.CASCADE),
            preserve_default=False,
        ),
    ]
