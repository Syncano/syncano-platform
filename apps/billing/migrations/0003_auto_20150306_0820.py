# -*- coding: utf-8 -*-
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('billing', '0002_auto_20150128_1538'),
    ]

    operations = [
        migrations.CreateModel(
            name='PricingPlan',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('code_name', models.CharField(max_length=255)),
                ('verbose_name', models.CharField(max_length=255)),
                ('available', models.BooleanField(default=True)),
            ],
            options={
                'ordering': ('id',),
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='Subscription',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('start', models.DateField()),
                ('admin', models.ForeignKey(related_name='subscriptions', to=settings.AUTH_USER_MODEL, on_delete=models.CASCADE)),
                ('pricing_plan', models.ForeignKey(to='billing.PricingPlan', on_delete=models.CASCADE)),
            ],
            options={
                'ordering': ('admin', 'start'),
            },
            bases=(models.Model,),
        ),
        migrations.AlterUniqueTogether(
            name='subscription',
            unique_together=set([('admin', 'start')]),
        ),
        migrations.AddField(
            model_name='pricingplan',
            name='admins',
            field=models.ManyToManyField(to=settings.AUTH_USER_MODEL, through='billing.Subscription'),
            preserve_default=True,
        ),
    ]
