# -*- coding: utf-8 -*-
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('invitations', '0007_admin_data'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='invitation',
            unique_together=set([('email', 'instance')]),
        ),
        migrations.AlterIndexTogether(
            name='invitation',
            index_together=set([]),
        ),
    ]
