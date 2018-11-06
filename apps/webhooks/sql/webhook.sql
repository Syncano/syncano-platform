CREATE INDEX webhook_acl_users ON webhooks_webhook
USING GIN (_users);

CREATE INDEX webhook_acl_groups ON webhooks_webhook
USING GIN (_groups);

CREATE INDEX webhook_acl_public ON webhooks_webhook
USING BTREE (_public) WHERE _public = true;
