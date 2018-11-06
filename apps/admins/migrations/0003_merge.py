# -*- coding: utf-8 -*-
from django.conf import settings
from django.db import migrations, models

import apps.core.fields


class Migration(migrations.Migration):

    dependencies = [
        ('admins', '0002_created_at'),
    ]

    operations = [
        migrations.CreateModel(
            name='AdminActivationKey',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('used', models.BooleanField(default=True)),
                ('key', apps.core.fields.LowercaseCharField(unique=True, max_length=40)),
                ('admin', models.ForeignKey(to=settings.AUTH_USER_MODEL, on_delete=models.CASCADE)),
                ],
            options={
                'abstract': False,
                },
            bases=(models.Model,),
        ),
        migrations.AlterField(
            model_name='admin',
            name='is_active',
            field=models.BooleanField(default=False, help_text='Designates whether this user should be treated as active. Unselect this instead of deleting accounts.', verbose_name='active'),
            preserve_default=True,
        ),
    ]
