from django.db import migrations

import apps.core.fields


class Migration(migrations.Migration):

    dependencies = [
        ('sockets', '0018_socket_checksum'),
    ]

    operations = [
        migrations.AddField(
            model_name='socket',
            name='install_config',
            field=apps.core.fields.NullableJSONField(blank=True, default={}, null=True),
        ),
    ]
