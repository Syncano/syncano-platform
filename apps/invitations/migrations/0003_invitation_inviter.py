# -*- coding: utf-8 -*-
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('invitations', '0002_auto_20150130_1243'),
    ]

    operations = [
        migrations.AddField(
            model_name='invitation',
            name='inviter',
            field=models.ForeignKey(related_name='sent_invitations', to=settings.AUTH_USER_MODEL, null=True, on_delete=models.CASCADE),
            preserve_default=True,
        ),
    ]
