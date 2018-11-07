# -*- coding: utf-8 -*-
import datetime

from django.db import migrations, models
from django.utils.timezone import utc


class Migration(migrations.Migration):

    dependencies = [
        ('invitations', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='invitation',
            name='state',
            field=models.SmallIntegerField(default=1, choices=[(1, 'new'), (2, 'declined'), (3, 'accepted')]),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='invitation',
            name='updated_at',
            field=models.DateTimeField(default=datetime.datetime(2015, 1, 30, 12, 43, 4, 868397, tzinfo=utc), auto_now=True),
            preserve_default=False,
        ),
        migrations.AlterIndexTogether(
            name='invitation',
            index_together=set([('email', 'state')]),
        ),
    ]
