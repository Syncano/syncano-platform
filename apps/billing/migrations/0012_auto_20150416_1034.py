# -*- coding: utf-8 -*-
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0011_auto_20150413_1236'),
    ]

    operations = [
        migrations.AddField(
            model_name='profile',
            name='address_city',
            field=models.CharField(max_length=100, blank=True),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='profile',
            name='address_country',
            field=models.CharField(max_length=35, blank=True),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='profile',
            name='address_line1',
            field=models.CharField(max_length=150, blank=True),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='profile',
            name='address_line2',
            field=models.CharField(max_length=150, blank=True),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='profile',
            name='address_state',
            field=models.CharField(max_length=100, blank=True),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='profile',
            name='address_zip',
            field=models.CharField(max_length=10, blank=True),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='profile',
            name='company_name',
            field=models.CharField(max_length=150, blank=True),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='profile',
            name='first_name',
            field=models.CharField(max_length=35, blank=True),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='profile',
            name='last_name',
            field=models.CharField(max_length=35, blank=True),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='profile',
            name='tax_number',
            field=models.CharField(max_length=50, blank=True),
            preserve_default=True,
        ),
    ]
