# -*- coding: utf-8 -*-
from django.db import migrations

from apps.response_templates.predefined_templates import PredefinedTemplates


def create_default_templates(apps, schema_editor):
    ResponseTemplate = apps.get_model('response_templates.ResponseTemplate')
    PredefinedTemplates.create_template_responses(check=True, model=ResponseTemplate)


class Migration(migrations.Migration):

    dependencies = [
        ('response_templates', '0002_auto_20151218_1535'),
    ]

    operations = [
         migrations.RunPython(create_default_templates),
    ]
