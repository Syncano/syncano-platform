from django.db import migrations

import apps.core.fields


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0013_group_name'),
    ]

    operations = [
        migrations.RunSQL("""
DROP INDEX IF EXISTS user_username_like;
DROP INDEX IF EXISTS group_acl_public;
DROP INDEX IF EXISTS group_acl_users;
DROP INDEX IF EXISTS group_acl_groups;
"""),
        migrations.RunSQL("""
CREATE INDEX user_username_like ON users_user
USING GIN (username gin_trgm_ops);

CREATE INDEX group_acl_users ON users_group
USING GIN (_users);

CREATE INDEX group_acl_groups ON users_group
USING GIN (_groups);

CREATE INDEX group_acl_public ON users_group
USING BTREE (_public) WHERE _public = true;
"""),
        migrations.AlterField(
            model_name='user',
            name='username',
            field=apps.core.fields.LowercaseCharField(db_index=True, max_length=64),
        ),
    ]
