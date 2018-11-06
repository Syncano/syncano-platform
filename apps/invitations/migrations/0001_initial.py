# -*- coding: utf-8 -*-
from django.db import migrations, models

import apps.core.fields


class Migration(migrations.Migration):

    dependencies = [
        ('admins', '0001_initial'),
        ('instances', '__first__'),
    ]

    operations = [
        migrations.CreateModel(
            name='Invitation',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('email', models.EmailField(max_length=254)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('key', apps.core.fields.LowercaseCharField(unique=True, max_length=40)),
                ('instance', models.ForeignKey(to='instances.Instance', on_delete=models.CASCADE)),
                ('role', models.ForeignKey(to='admins.Role', on_delete=models.CASCADE)),
            ],
            options={
                'ordering': ('id',),
            },
            bases=(models.Model,),
        ),
        migrations.AlterUniqueTogether(
            name='invitation',
            unique_together=set([('email', 'instance')]),
        ),
    ]
