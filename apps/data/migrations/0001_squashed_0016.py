# -*- coding: utf-8 -*-
import django.core.validators
import django.db.models.deletion
import jsonfield.fields
from django.db import migrations, models

import apps.core.fields
import apps.core.validators
import apps.data.fields


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ('users', '__first__'),
        ('channels', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='DataObject',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('_data', apps.core.fields.DictionaryField()),
                ('_files', apps.core.fields.DictionaryField()),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('updated_at', models.DateTimeField(auto_now=True, db_index=True)),
                ('revision', models.IntegerField(db_index=True, default=1)),
                ('owner_permissions', models.SmallIntegerField(choices=[(0, 'none'), (1, 'read'), (2, 'write'), (3, 'full')], db_index=True, default=3)),
                ('group_permissions', models.SmallIntegerField(choices=[(0, 'none'), (1, 'read'), (2, 'write'), (3, 'full')], db_index=True, default=0)),
                ('other_permissions', models.SmallIntegerField(choices=[(0, 'none'), (1, 'read'), (2, 'write'), (3, 'full')], db_index=True, default=0)),
                ('channel_room', models.CharField(blank=True, db_index=True, default=None, max_length=64, null=True)),
                ('_is_live', apps.core.fields.LiveField(db_index=True, default=True)),
            ],
            options={
                'ordering': ('id',),
                'verbose_name': 'DataObject',
            },
        ),
        migrations.CreateModel(
            name='Klass',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('metadata', jsonfield.fields.JSONField(blank=True, default={})),
                ('description', models.TextField(blank=True, max_length=256)),
                ('name', apps.core.fields.StrippedSlugField(max_length=64, validators=[apps.core.validators.NotInValidator(values={'self', 'user', 'users', 'acl'})])),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('revision', models.IntegerField(default=1)),
                ('schema', jsonfield.fields.JSONField(default=[])),
                ('mapping', apps.core.fields.DictionaryField()),
                ('existing_indexes', jsonfield.fields.JSONField(default={})),
                ('index_changes', jsonfield.fields.JSONField(null=True)),
                ('group_permissions', models.SmallIntegerField(choices=[(0, 'none'), (1, 'read'), (2, 'create_objects')], db_index=True, default=2)),
                ('other_permissions', models.SmallIntegerField(choices=[(0, 'none'), (1, 'read'), (2, 'create_objects')], db_index=True, default=2)),
                ('_is_live', apps.core.fields.LiveField(default=True)),
                ('group', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='users.Group')),
            ],
            options={
                'ordering': ('id',),
                'verbose_name': 'Class',
                'verbose_name_plural': 'Classes',
            },
        ),
        migrations.AddField(
            model_name='dataobject',
            name='_klass',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='data_objects', to='data.Klass'),
        ),
        migrations.AddField(
            model_name='dataobject',
            name='channel',
            field=models.ForeignKey(blank=True, default=None, null=True, on_delete=django.db.models.deletion.CASCADE, to='channels.Channel'),
        ),
        migrations.AddField(
            model_name='dataobject',
            name='group',
            field=models.ForeignKey(blank=True, default=None, null=True, on_delete=django.db.models.deletion.SET_NULL, to='users.Group'),
        ),
        migrations.AddField(
            model_name='dataobject',
            name='owner',
            field=models.ForeignKey(blank=True, default=None, null=True, on_delete=django.db.models.deletion.CASCADE, to='users.User'),
        ),
        migrations.AlterUniqueTogether(
            name='klass',
            unique_together=set([('name', '_is_live')]),
        ),
        migrations.RunSQL("""
-- klasses
CREATE INDEX class_name_like ON data_klass
USING BTREE (name varchar_pattern_ops);

-- dataobjects
CREATE FUNCTION to_timestamp(TEXT)
  RETURNS TIMESTAMPTZ AS $$
SELECT $1 :: TIMESTAMP AT TIME ZONE 'utc';
$$ LANGUAGE SQL IMMUTABLE;

CREATE FUNCTION count_estimate(query TEXT, real_limit INT DEFAULT 1000)
  RETURNS INTEGER AS
  $func$
  DECLARE
    rec       RECORD;
    count_rec RECORD;
    ret       INTEGER;
  BEGIN
    EXECUTE 'SELECT COUNT(*) FROM (' || query || ' LIMIT ' || real_limit + 1 || ') c'
    INTO count_rec;
    IF count_rec.count <= real_limit
    THEN
      RETURN count_rec.count;
    END IF;
    FOR rec IN EXECUTE 'EXPLAIN ' || query LOOP
      ret := SUBSTRING(rec."QUERY PLAN" FROM ' rows=([[:digit:]]+)');
      EXIT WHEN ret IS NOT NULL;
    END LOOP;

    RETURN GREATEST(ret, real_limit);
  END
  $func$ LANGUAGE plpgsql;
"""
)
    ]
