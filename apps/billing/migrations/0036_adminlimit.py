# -*- coding: utf-8 -*-
from django.db import migrations, models

import apps.data.fields


class Migration(migrations.Migration):

    dependencies = [
        ('admins', '0011_length'),
        ('billing', '0035_price_digits'),
    ]

    operations = [
        migrations.CreateModel(
            name='AdminLimit',
            fields=[
                ('admin', models.OneToOneField(related_name='admin_limit', primary_key=True, serialize=False, to='admins.Admin', on_delete=models.CASCADE)),
                ('limits', apps.core.fields.DictionaryField(verbose_name='limits', null=True, editable=False)),
            ],
            options={
            },
            bases=(models.Model,),
        ),
    ]
