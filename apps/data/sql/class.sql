CREATE INDEX class_name_like ON data_klass
USING BTREE (name varchar_pattern_ops);

CREATE INDEX klass_acl_users ON data_klass
USING GIN (_users);

CREATE INDEX klass_acl_groups ON data_klass
USING GIN (_groups);

CREATE INDEX klass_acl_public ON data_klass
USING BTREE (_public) WHERE _public = true;
