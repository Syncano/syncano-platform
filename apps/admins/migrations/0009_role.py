# -*- coding: utf-8 -*-
from django.core.management import call_command
from django.db import migrations, models


def load_fixtures(apps, schema_editor):
    call_command('loaddata', 'core_data', verbosity=0, app_label='admins', ignorenonexistent=True)


class Migration(migrations.Migration):
    dependencies = [
        ('admins', '0008_auto_20150429_1512'),
        ('invitations', '0004_role_as_integer'),
    ]

    operations = [
        migrations.AlterField(
            model_name='admininstancerole',
            name='role',
            field=models.IntegerField()
        ),
        migrations.RunSQL(
            "DROP TABLE IF EXISTS admins_role;"
        ),
        migrations.CreateModel(
            name='Role',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('name', models.CharField(unique=True, max_length=64, verbose_name='name',
                                          choices=[(1, 'full'), (2, 'write'), (3, 'read')])),
            ],
            options={
                'ordering': ('id',),
            },
            bases=(models.Model,),
        ),
        migrations.RemoveField(
            model_name='admininstancerole',
            name='permissions_updated',
        ),
        migrations.RunPython(load_fixtures)
    ]
