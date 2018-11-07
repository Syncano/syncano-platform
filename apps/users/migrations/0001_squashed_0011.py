# -*- coding: utf-8 -*-
import django.core.validators
import django.db.models.deletion
from django.db import migrations, models

import apps.core.fields


class Migration(migrations.Migration):
    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Group',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('label', models.CharField(blank=True, max_length=64)),
                ('description', models.TextField(blank=True, max_length=256)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('_is_live', apps.core.fields.LiveField(db_index=True, default=True)),
            ],
            options={
                'ordering': ('id',),
            },
        ),
        migrations.CreateModel(
            name='Membership',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('group', models.ForeignKey(to='users.Group', on_delete=models.CASCADE)),
            ],
            options={
                'ordering': ('id',),
            },
        ),
        migrations.CreateModel(
            name='User',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('username', apps.core.fields.LowercaseCharField(max_length=64)),
                ('password', models.CharField(max_length=128)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('_is_live', apps.core.fields.LiveField(default=True)),
                ('key', apps.core.fields.LowercaseCharField(max_length=40)),
                ('groups', models.ManyToManyField(to='users.Group', through='users.Membership'))
            ],
            options={
                'ordering': ('id',),
            },
        ),
        migrations.CreateModel(
            name='UserSocialProfile',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='social_profiles', to='users.User')),
                ('backend', models.SmallIntegerField(choices=[(0, 'facebook'), (1, 'google-oauth2'), (2, 'github'), (3, 'linkedin'), (4, 'twitter')])),
                ('social_id', models.CharField(max_length=32)),
            ],
            options={
                'ordering': ('id',),
                'abstract': False,
                'verbose_name': 'User Social Profile',
            },
        ),
        migrations.AlterUniqueTogether(
            name='user',
            unique_together=set([('username', '_is_live')]),
        ),
        migrations.AddField(
            model_name='membership',
            name='user',
            field=models.ForeignKey(to='users.User', on_delete=models.CASCADE),
            preserve_default=True,
        ),
        migrations.AlterUniqueTogether(
            name='membership',
            unique_together=set([('user', 'group')]),
        ),
        migrations.AlterUniqueTogether(
            name='usersocialprofile',
            unique_together=set([('backend', 'social_id')]),
        ),
    ]
