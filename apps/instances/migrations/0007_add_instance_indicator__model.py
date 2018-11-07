# -*- coding: utf-8 -*-
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('instances', '0006_length'),
    ]

    operations = [
        migrations.CreateModel(
            name='InstanceIndicator',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('type', models.SmallIntegerField(choices=[(0, 'schedules_count'), (1, 'storage_size')])),
                ('value', models.BigIntegerField(default=0)),
                ('instance', models.ForeignKey(related_name='indicators', to='instances.Instance', on_delete=models.CASCADE)),
            ],
            options={
                'ordering': ('id',),
            },
            bases=(models.Model,),
        ),
        migrations.AlterUniqueTogether(
            name='instanceindicator',
            unique_together=set([('instance', 'type')]),
        ),
        migrations.AlterIndexTogether(
            name='instanceindicator',
            index_together=set([('type', 'value')]),
        ),
    ]
