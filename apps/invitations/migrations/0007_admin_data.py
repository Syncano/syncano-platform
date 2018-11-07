# -*- coding: utf-8 -*-
from django.db import migrations


def connect_invitations(apps, schema_editor):
    Admin = apps.get_model('admins.Admin')
    Invitation = apps.get_model('invitations.Invitation')
    for invitation in Invitation.objects.iterator():
        try:
            invitation.admin = Admin.objects.get(email__iexact=invitation.email)
            invitation.save(update_fields=('admin',))
        except Admin.DoesNotExist:
            pass


class Migration(migrations.Migration):
    dependencies = [
        ('admins', '0003_merge'),
        ('invitations', '0006_invitation_admin'),
    ]

    operations = [
        migrations.RunPython(connect_invitations),
    ]
