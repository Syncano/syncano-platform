# -*- coding: utf-8 -*-
from django.db import migrations, models
from django.utils.text import slugify

from apps.core.fields import LiveField, LowercaseCharField


def fill_hosting_names(apps, schema_editor):
    Hosting = apps.get_model("hosting", "Hosting")
    for hosting in Hosting.objects.all():
        slug_name = slugify(hosting.name)

        if Hosting.objects.filter(name=slug_name).exists():
            slug_name = "{}{}".format(slug_name, hosting.id)

        hosting.name = slug_name
        hosting.save()


class Migration(migrations.Migration):

    dependencies = [
        ('hosting', '0002_hosting_domains'),
    ]

    operations = [
        migrations.RenameField(
            model_name='hosting',
            old_name='label',
            new_name='name'
        ),
        migrations.RunPython(fill_hosting_names),
        migrations.AlterField(
            model_name='hosting',
            name='name',
            field=LowercaseCharField(max_length=253),
        ),
        migrations.AlterField(
            model_name='hosting',
            name='_is_live',
            field=LiveField(default=True),
        ),
        migrations.AlterUniqueTogether(
            name='hosting',
            unique_together=set([('name', '_is_live')]),
        ),
    ]
