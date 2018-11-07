# -*- coding: utf-8 -*-
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

import apps.core.fields


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('invitations', '0005_role_as_fk'),
    ]

    operations = [
        migrations.AddField(
            model_name='invitation',
            name='admin',
            field=models.ForeignKey(on_delete=django.db.models.deletion.SET_NULL, default=None, to=settings.AUTH_USER_MODEL, blank=True, null=True),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='invitation',
            name='email',
            field=apps.core.fields.LowercaseEmailField(max_length=254),
            preserve_default=True,
        ),
        migrations.AlterIndexTogether(
            name='invitation',
            index_together=set([('admin', 'state')]),
        ),
        migrations.AlterUniqueTogether(
            name='invitation',
            unique_together=set([('admin', 'instance'), ('email', 'instance')]),
        ),
    ]
