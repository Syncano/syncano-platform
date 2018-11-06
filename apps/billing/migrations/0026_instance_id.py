# -*- coding: utf-8 -*-
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('billing', '0025_auto_20150512_1153'),
    ]

    operations = [
        migrations.AlterField(
            model_name='invoiceitem',
            name='instance',
            field=models.IntegerField(default=1),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name='transaction',
            name='instance',
            field=models.IntegerField(default=1),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name='invoiceitem',
            name='source',
            field=models.SmallIntegerField(choices=[(0, b'Data Call'), (1, b'CodeBox Call')]),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='transaction',
            name='source',
            field=models.SmallIntegerField(choices=[(0, b'Data Call'), (1, b'CodeBox Call')]),
            preserve_default=True,
        ),
        migrations.RenameField(
            model_name='invoiceitem',
            old_name='instance',
            new_name='instance_id',
        ),
        migrations.RenameField(
            model_name='transaction',
            old_name='instance',
            new_name='instance_id',
        ),
    ]
