# -*- coding: utf-8 -*-
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models

import apps.core.fields


class Migration(migrations.Migration):

    dependencies = [
        ('instances', '__first__'),
    ]

    operations = [
        migrations.CreateModel(
            name='Admin',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('password', models.CharField(max_length=128, verbose_name='password')),
                ('last_login', models.DateTimeField(default=django.utils.timezone.now, verbose_name='last login')),
                ('email', apps.core.fields.LowercaseEmailField(max_length=254, verbose_name='email address')),
                ('first_name', models.CharField(max_length=35, verbose_name='first name', blank=True)),
                ('last_name', models.CharField(max_length=35, verbose_name='last name', blank=True)),
                ('is_staff', models.BooleanField(default=False, help_text='Designates whether the user can log into this admin site.', verbose_name='staff status')),
                ('is_active', models.BooleanField(default=True, help_text='Designates whether this user should be treated as active. Unselect this instead of deleting accounts.', verbose_name='active')),
                ('is_superuser', models.BooleanField(default=False, help_text='Designates that this user has all permissions without explicitly assigning them.', verbose_name='superuser status')),
                ('date_joined', models.DateTimeField(default=django.utils.timezone.now, verbose_name='date joined')),
                ('_is_live', apps.core.fields.LiveField(default=True)),
                ('key', apps.core.fields.LowercaseCharField(max_length=40)),
            ],
            options={
                'ordering': ('id',),
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='AdminInstanceRole',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('permissions_updated', models.DateTimeField(auto_now_add=True)),
                ('admin', models.ForeignKey(related_name='instance_roles', to=settings.AUTH_USER_MODEL, on_delete=models.CASCADE)),
                ('instance', models.ForeignKey(related_name='admin_roles', to='instances.Instance', on_delete=models.CASCADE)),
            ],
            options={
                'ordering': ('id',),
            },
            bases=(models.Model,),
        ),
        migrations.AlterUniqueTogether(
            name='admin',
            unique_together=set([('email', '_is_live')]),
        ),
        migrations.CreateModel(
            name='Role',
            fields=[
            ],
            options={
                'ordering': ('id',),
            },
            bases=(models.Model,),
        ),
        migrations.AddField(
            model_name='admininstancerole',
            name='role',
            field=models.ForeignKey(related_name='instance_admins', to='admins.Role', on_delete=models.CASCADE),
            preserve_default=True,
        ),
        migrations.AlterUniqueTogether(
            name='admininstancerole',
            unique_together=set([('admin', 'instance')]),
        ),
    ]
