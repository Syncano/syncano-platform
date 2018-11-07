# -*- coding: utf-8 -*-
from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0030_free_plan'),
    ]

    operations = [
        migrations.RenameField(
            model_name='invoice',
            old_name='amount',
            new_name='overage_amount',
        ),
        migrations.AddField(
            model_name='invoice',
            name='plan_fee',
            field=models.DecimalField(default=0, max_digits=10, decimal_places=2),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='invoice',
            name='status',
            field=models.SmallIntegerField(default=0, db_index=True, choices=[(0, 'new'), (1, 'pending'), (2, 'fake'), (3, 'empty'), (4, 'scheduling failed'), (5, 'payment scheduled'), (6, 'payment failed'), (7, 'payment succeeded')]),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='invoiceitem',
            name='source',
            field=models.CharField(max_length=3, choices=[('fee', b'Plan Fee'), ('cbx', b'CodeBox Executions'), ('api', b'API Call')]),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='transaction',
            name='source',
            field=models.CharField(max_length=3, choices=[('cbx', b'script execution'), ('api', b'api call')]),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='invoice',
            name='overage_amount',
            field=models.DecimalField(default=0, max_digits=15, decimal_places=7),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='subscription',
            name='end',
            field=models.DateField(null=True, blank=True),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='subscription',
            name='start',
            field=models.DateField(),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='invoiceitem',
            name='instance_id',
            field=models.IntegerField(null=True, db_index=True),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='invoiceitem',
            name='instance_name',
            field=models.CharField(max_length=64, null=True),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='invoiceitem',
            name='price',
            field=models.DecimalField(default=Decimal('0'), max_digits=10, decimal_places=7),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='invoice',
            name='due_date',
            field=models.DateField(),
            preserve_default=True,
        ),
        migrations.AlterIndexTogether(
            name='invoice',
            index_together=set([('admin', 'status', 'due_date')]),
        ),
        migrations.AlterField(
            model_name='transaction',
            name='period',
            field=models.DateTimeField(),
            preserve_default=True,
        ),
        migrations.AlterModelOptions(
            name='invoice',
            options={'ordering': ('-id',)},
        ),
    ]
