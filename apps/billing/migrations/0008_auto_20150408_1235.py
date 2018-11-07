# -*- coding: utf-8 -*-
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0007_auto_20150403_1434'),
    ]

    operations = [
        migrations.AlterField(
            model_name='profile',
            name='admin',
            field=models.OneToOneField(related_name='billing_profile', primary_key=True, serialize=False, to=settings.AUTH_USER_MODEL, on_delete=models.CASCADE),
            preserve_default=True,
        ),
    ]
