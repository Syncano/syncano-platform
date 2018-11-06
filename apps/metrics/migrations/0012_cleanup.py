# -*- coding: utf-8 -*-
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('admins', '0010_role_as_fk'),
    ]

    operations = [
        migrations.CreateModel(
            name='DayAggregate',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('timestamp', models.DateTimeField(db_index=True)),
                ('source', models.SmallIntegerField(choices=[(0, b'Data Call'), (1, b'CodeBox Call')])),
                ('instance_id', models.IntegerField(null=True)),
                ('instance_name', models.CharField(max_length=64, null=True)),
                ('value', models.IntegerField()),
                ('admin', models.ForeignKey(on_delete=django.db.models.deletion.SET_NULL, blank=True, to='admins.Admin', null=True)),
            ],
            options={
                'abstract': False,
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='HourAggregate',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('timestamp', models.DateTimeField(db_index=True)),
                ('source', models.SmallIntegerField(choices=[(0, b'Data Call'), (1, b'CodeBox Call')])),
                ('instance_id', models.IntegerField(null=True)),
                ('instance_name', models.CharField(max_length=64, null=True)),
                ('value', models.IntegerField()),
                ('admin', models.ForeignKey(on_delete=django.db.models.deletion.SET_NULL, blank=True, to='admins.Admin', null=True)),
            ],
            options={
                'abstract': False,
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='MinuteAggregate',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('timestamp', models.DateTimeField(db_index=True)),
                ('source', models.SmallIntegerField(choices=[(0, b'Data Call'), (1, b'CodeBox Call')])),
                ('instance_id', models.IntegerField(null=True)),
                ('instance_name', models.CharField(max_length=64, null=True)),
                ('value', models.IntegerField()),
                ('admin', models.ForeignKey(on_delete=django.db.models.deletion.SET_NULL, blank=True, to='admins.Admin', null=True)),
            ],
            options={
                'abstract': False,
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='WorkLogEntry',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('left_boundary', models.DateTimeField()),
                ('right_boundary', models.DateTimeField(db_index=True)),
                ('seconds', models.IntegerField(db_index=True, null=True, blank=True)),
                ('status', models.SmallIntegerField(default=0, choices=[(0, 'queued'), (1, 'done'), (2, 'failed')])),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
            },
            bases=(models.Model,),
        ),
        migrations.AlterUniqueTogether(
            name='worklogentry',
            unique_together=set([('left_boundary', 'right_boundary')]),
        ),
    ]
