# -*- coding: utf-8 -*-
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('high_level', '0002_dataobjecthighlevelapi_query'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='dataobjecthighlevelapi',
            name='_is_live',
        ),
        migrations.AlterField(
            model_name='dataobjecthighlevelapi',
            name='description',
            field=models.TextField(max_length=256, blank=True),
            preserve_default=True,
        ),
        migrations.AlterModelOptions(
            name='dataobjecthighlevelapi',
            options={'ordering': ('id',), 'verbose_name': 'Data Endpoint'},
        ),
    ]
