# -*- coding: utf-8 -*-
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('codeboxes', '0036_codeboxschedule_socket'),
    ]

    operations = [
        migrations.AddField(
            model_name='codebox',
            name='checksum',
            field=models.CharField(blank=True, default=None, max_length=32, null=True),
        ),
        migrations.AlterIndexTogether(
            name='codebox',
            index_together=set([('socket', 'checksum')]),
        ),
    ]
