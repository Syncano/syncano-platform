# -*- coding: utf-8 -*-
import django.core.validators
import jsonfield
from django.db import migrations, models

import apps.core.fields
import apps.data.fields


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0001_squashed_0011'),
    ]

    operations = [
        migrations.CreateModel(
            name='Change',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('room', apps.core.fields.LowercaseCharField(max_length=50, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('action', models.SmallIntegerField(default=0, choices=[(0, 'custom'), (1, 'create'), (2, 'update'), (3, 'delete')])),
                ('author', jsonfield.JSONField(default={})),
                ('metadata', jsonfield.JSONField(null=True)),
                ('payload', jsonfield.JSONField(null=True)),
            ],
            options={
                'ordering': ('-id',),
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='Channel',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('name', apps.core.fields.StrippedSlugField(max_length=50, validators=[django.core.validators.MinLengthValidator(3)])),
                ('type', models.SmallIntegerField(default=0, choices=[(0, 'default'), (1, 'separate_rooms')])),
                ('options', apps.core.fields.DictionaryField(verbose_name='options', null=True, editable=False)),
                ('group_permissions', models.SmallIntegerField(default=0, db_index=True, choices=[(0, 'none'), (1, 'subscribe'), (2, 'publish')])),
                ('other_permissions', models.SmallIntegerField(default=0, db_index=True, choices=[(0, 'none'), (1, 'subscribe'), (2, 'publish')])),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('_is_live', apps.core.fields.LiveField(default=True)),
                ('group', models.ForeignKey(blank=True, to='users.Group', null=True, on_delete=models.CASCADE)),
            ],
            options={
                'ordering': ('id',),
            },
            bases=(models.Model,),
        ),
        migrations.AlterUniqueTogether(
            name='channel',
            unique_together=set([('name', '_is_live')]),
        ),
        migrations.AddField(
            model_name='change',
            name='channel',
            field=models.ForeignKey(to='channels.Channel', on_delete=models.CASCADE),
            preserve_default=True,
        ),
        migrations.AlterIndexTogether(
            name='change',
            index_together=set([('channel', 'room')]),
        ),
    ]
