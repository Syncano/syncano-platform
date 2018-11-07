# -*- coding: utf-8 -*-
import jsonfield.fields
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('sockets', '0012_add_installed'),
    ]

    operations = [
        migrations.AlterField(
            model_name='socket',
            name='status_info',
            field=jsonfield.fields.JSONField(default=None, null=True),
        ),
        migrations.RunSQL(
            """
            UPDATE sockets_socket SET status_info=NULL
            """
        ),
    ]
