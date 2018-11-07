# -*- coding: utf-8 -*-
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ('codeboxes', '__first__'),
        ('data', '__first__'),
    ]

    operations = [
        migrations.CreateModel(
            name='Trigger',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('signal', models.CharField(choices=[('post_update', 'post_update'), ('post_create', 'post_create'),
                                                     ('post_delete', 'post_delete')], max_length=20)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('codebox', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='event_tasks',
                                              to='codeboxes.CodeBox')),
                ('klass', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='data.Klass')),
                ('label', models.CharField(blank=True, max_length=64)),
                ('description', models.TextField(blank=True, max_length=256)),
            ],
            options={
                'ordering': ('id',),
            },
        ),
        migrations.AlterIndexTogether(
            name='trigger',
            index_together=set([('signal', 'klass')]),
        ),
    ]
