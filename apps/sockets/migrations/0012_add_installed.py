# -*- coding: utf-8 -*-
import re

import django.core.validators
from django.db import migrations, models

import apps.core.fields
import apps.core.validators
from apps.core.helpers import generate_key


def create_unique_key(apps, schema_editor):
    Socket = apps.get_model('sockets.Socket')
    for socket in Socket.objects.all().iterator():
        socket.key = generate_key()
        socket.save(update_fields=('key',))


class Migration(migrations.Migration):
    dependencies = [
        ('sockets', '0011_socket_handler'),
    ]

    operations = [
        migrations.AddField(
            model_name='socket',
            name='file_list',
            field=apps.core.fields.NullableJSONField(blank=True, default={}, null=True),
        ),
        migrations.AddField(
            model_name='socket',
            name='installed',
            field=apps.core.fields.NullableJSONField(blank=True, default={}, null=True),
        ),
        migrations.AddField(
            model_name='socket',
            name='key',
            field=apps.core.fields.LowercaseCharField(default='abc', max_length=40),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='socket',
            name='size',
            field=models.IntegerField(default=0),
        ),
        migrations.AlterField(
            model_name='socketendpoint',
            name='name',
            field=apps.core.fields.StrippedSlugField(max_length=256, unique=True, validators=[apps.core.validators.NotInValidator(values=set(['install'])), django.core.validators.RegexValidator(inverse_match=True, message='Value cannot end with history, traces.', regex=re.compile('/(history|traces)$', 32))]),
        ),
        migrations.RemoveField(
            model_name='socket',
            name='installed_deps',
        ),
        migrations.RunPython(
            create_unique_key
        ),
        migrations.AlterUniqueTogether(
            name='socket',
            unique_together=set([('key', '_is_live'), ('name', '_is_live')]),
        ),
    ]
