CREATE INDEX subscription_range ON billing_subscription
USING GIST (range);
