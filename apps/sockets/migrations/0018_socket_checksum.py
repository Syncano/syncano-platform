# -*- coding: utf-8 -*-
import random
from hashlib import md5

from django.db import migrations, models


def update_socket_hash(apps, schema_editor):
    Socket = apps.get_model('sockets.Socket')
    for socket in Socket.objects.all():
        hash_md5 = md5()
        for _, f in sorted(socket.file_list.items()):
            hash_md5.update(f['checksum'].encode())
        socket.checksum = hash_md5.hexdigest()
        socket.save(update_fields=('checksum',))

    SocketEnvironment = apps.get_model('sockets.SocketEnvironment')
    for env in SocketEnvironment.objects.all():
        if env.checksum is None:
            if env.fs_file:
                env.checksum = md5(env.fs_file.url.encode()).hexdigest()
            else:
                env.checksum = hex(random.getrandbits(128))[2:-1]
            env.save(update_fields=('checksum',))


class Migration(migrations.Migration):

    dependencies = [
        ('sockets', '0017_socketenvironment_name_unique'),
    ]

    operations = [
        migrations.AddField(
            model_name='socket',
            name='checksum',
            field=models.CharField(max_length=32, null=True),
        ),
        migrations.RunPython(update_socket_hash),
    ]
