# -*- coding: utf-8 -*-
# Generated by Django 1.9.2 on 2016-02-18 13:42
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0043_auto_20160210_1504'),
    ]

    operations = [
        migrations.AlterField(
            model_name='invoiceitem',
            name='source',
            field=models.CharField(choices=[('api', 'API Call'), ('cbx', 'Script Execution Time (s)'), ('fee', 'Plan Fee')], max_length=3),
        ),
        migrations.AlterField(
            model_name='transaction',
            name='source',
            field=models.CharField(choices=[('api', 'api call'), ('cbx', 'script execution time')], max_length=3),
        ),
        migrations.RunSQL(
            """UPDATE billing_invoiceitem SET quantity = quantity * 12 WHERE source='cbx'"""
        ),
        migrations.RunSQL(
            """UPDATE billing_transaction SET quantity = quantity * 12 WHERE source='cbx'"""
        ),
    ]
