# -*- coding: utf-8 -*-
# Generated by Django 1.9.8 on 2016-09-07 14:23
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('response_templates', '0003_add_default_reponse_templates'),
    ]

    operations = [
        migrations.AddField(
            model_name='responsetemplate',
            name='description',
            field=models.TextField(blank=True, max_length=256),
        ),
    ]
