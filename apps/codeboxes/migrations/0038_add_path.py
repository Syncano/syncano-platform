# -*- coding: utf-8 -*-
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('codeboxes', '0037_add_checksum'),
    ]

    operations = [
        migrations.AddField(
            model_name='codebox',
            name='path',
            field=models.TextField(blank=True, default=None, max_length=300, null=True),
        ),
        migrations.AlterIndexTogether(
            name='codebox',
            index_together=set([('socket', 'path')]),
        ),
        migrations.RunSQL(
          """
          UPDATE codeboxes_codebox SET path=checksum
          WHERE socket_id IS NOT NULL AND path IS NULL AND checksum IS NOT NULL
          """
        ),
    ]
