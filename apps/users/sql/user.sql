CREATE INDEX user_username_like ON users_user
USING GIN (username gin_trgm_ops);

CREATE INDEX group_acl_users ON users_group
USING GIN (_users);

CREATE INDEX group_acl_groups ON users_group
USING GIN (_groups);

CREATE INDEX group_acl_public ON users_group
USING BTREE (_public) WHERE _public = true;
