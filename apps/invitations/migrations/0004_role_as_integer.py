# -*- coding: utf-8 -*-
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('invitations', '0003_invitation_inviter'),
    ]

    operations = [
        migrations.AlterField(
            model_name='invitation',
            name='role',
            field=models.IntegerField()
        ),
    ]
