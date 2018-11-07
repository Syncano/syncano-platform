# -*- coding: utf-8 -*-
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('instances', '0002_auto_20150127_1552'),
    ]

    operations = [
        migrations.CreateModel(
            name='Coupon',
            fields=[
                ('name', models.CharField(max_length=32, unique=True, serialize=False, primary_key=True)),
                ('percent_off', models.SmallIntegerField(null=True)),
                ('amount_off', models.FloatField(null=True)),
                ('currency', models.CharField(default='USD', max_length=3, choices=[('usd', 'USD')])),
                ('duration', models.SmallIntegerField(default=1)),
                ('redeem_by', models.DateField()),
            ],
            options={
                'ordering': ('name',),
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='Discount',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('start', models.DateField(auto_now_add=True)),
                ('end', models.DateField()),
                ('coupon', models.ForeignKey(to='billing.Coupon', on_delete=models.CASCADE)),
                ('customer', models.ForeignKey(to=settings.AUTH_USER_MODEL, on_delete=models.CASCADE)),
                ('instance', models.ForeignKey(to='instances.Instance', on_delete=models.CASCADE)),
            ],
            options={
                'ordering': ('id',),
            },
            bases=(models.Model,),
        ),
        migrations.AlterUniqueTogether(
            name='discount',
            unique_together=set([('instance', 'coupon', 'customer')]),
        ),
    ]
