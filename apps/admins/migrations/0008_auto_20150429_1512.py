# -*- coding: utf-8 -*-
from django.conf import settings
from django.db import migrations, models

import apps.core.fields


class Migration(migrations.Migration):

    dependencies = [
        ('admins', '0007_auto_20150409_1234'),
    ]

    operations = [
        migrations.CreateModel(
            name='AdminSocialProfile',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('backend', models.SmallIntegerField(choices=[(0, 'facebook'), (1, 'google-oauth2'), (2, 'github')])),
                ('social_id', models.CharField(max_length=32)),
                ('email', apps.core.fields.LowercaseEmailField(max_length=254, verbose_name='email address')),
                ('admin', models.ForeignKey(related_name='social_profiles', to=settings.AUTH_USER_MODEL, on_delete=models.CASCADE)),
            ],
            options={
                'ordering': ('id',),
                'abstract': False,
            },
            bases=(models.Model,),
        ),
        migrations.AlterUniqueTogether(
            name='adminsocialprofile',
            unique_together=set([('backend', 'social_id')]),
        ),
    ]
