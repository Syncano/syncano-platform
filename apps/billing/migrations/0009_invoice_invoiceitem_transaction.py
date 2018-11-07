# -*- coding: utf-8 -*-
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

import apps.core.fields


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('instances', '0005_shorter_name'),
        ('billing', '0008_auto_20150408_1235'),
    ]

    operations = [
        migrations.CreateModel(
            name='Invoice',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('status', models.SmallIntegerField(default=0, choices=[(0, 'new'), (1, 'pending'), (2, b'payment succeeded'), (3, b'payment failed')])),
                ('amount', models.DecimalField(max_digits=12, decimal_places=2)),
                ('period', models.DateField()),
                ('external_id', models.CharField(max_length=18, blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('reference', apps.core.fields.LowercaseCharField(unique=True, max_length=40)),
                ('admin', models.ForeignKey(related_name='invoices', on_delete=django.db.models.deletion.SET_NULL, blank=True, to=settings.AUTH_USER_MODEL, null=True)),
            ],
            options={
                'abstract': False,
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='InvoiceItem',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('instance_name', models.CharField(max_length=50)),
                ('source', models.SmallIntegerField(choices=[(0, 'count'), (1, b'bytes sent')])),
                ('amount', models.DecimalField(max_digits=12, decimal_places=2)),
                ('quantity', models.IntegerField()),
                ('external_id', models.CharField(max_length=18, blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('reference', apps.core.fields.LowercaseCharField(unique=True, max_length=40)),
                ('instance', models.ForeignKey(related_name='invoice_items', on_delete=django.db.models.deletion.SET_NULL, blank=True, to='instances.Instance', null=True)),
                ('invoice', models.ForeignKey(related_name='items', to='billing.Invoice', on_delete=models.CASCADE)),
            ],
            options={
                'abstract': False,
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='Transaction',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('instance_name', models.CharField(max_length=50)),
                ('type', models.SmallIntegerField(choices=[(0, 'charge'), (1, 'refund'), (2, 'discount')])),
                ('source', models.SmallIntegerField(choices=[(0, 'count'), (1, b'bytes sent')])),
                ('amount', models.DecimalField(max_digits=12, decimal_places=2)),
                ('quantity', models.IntegerField()),
                ('period', models.DateField()),
                ('aggregated', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('admin', models.ForeignKey(related_name='transactions', on_delete=django.db.models.deletion.SET_NULL, blank=True, to=settings.AUTH_USER_MODEL, null=True)),
                ('instance', models.ForeignKey(related_name='transactions', on_delete=django.db.models.deletion.SET_NULL, blank=True, to='instances.Instance', null=True)),
            ],
            options={
            },
            bases=(models.Model,),
        ),
    ]
