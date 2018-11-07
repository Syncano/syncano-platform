CREATE INDEX channel_name_like ON channels_channel
USING BTREE (name varchar_pattern_ops);

CREATE INDEX channel_acl_users ON channels_channel
USING GIN (_users);

CREATE INDEX channel_acl_groups ON channels_channel
USING GIN (_groups);

CREATE INDEX channel_acl_public ON channels_channel
USING BTREE (_public) WHERE _public = true;
