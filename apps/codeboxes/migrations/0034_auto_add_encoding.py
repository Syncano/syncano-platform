# -*- coding: utf-8 -*-
import re

from django.db import migrations


def is_source_ok(src):
    # Check if source contains no UTF-8 or valid coding
    try:
        src.encode('ascii')
    except UnicodeEncodeError:
        # Check if first two lines contain a valid coding definition
        for line in src.split('\n', 2)[:2]:
            if re.match(r'^[ \t\v]*#.*?coding[:=][ \t]*([-_.a-zA-Z0-9]+)', line):
                return True
        return False
    return True

def add_encoding(apps, schema_editor):
    CodeBox = apps.get_model('codeboxes.CodeBox')
    for script in CodeBox.objects.filter(runtime_name__startswith='python'):
        if not is_source_ok(script.source):
            if '\r\n' in script.source:
                endline = '\r\n'
            else:
                endline = '\n'
            script.source = '# coding=UTF8{endline}{source}'.format(endline=endline, source=script.source)
            script.save(update_fields=('source',))


class Migration(migrations.Migration):

    dependencies = [
        ('codeboxes', '0033_runtimes'),
    ]

    operations = [
        # Add encoding to existing scripts so they won't blow up. It's no longer implicitly added.
        migrations.RunPython(add_encoding)
    ]
