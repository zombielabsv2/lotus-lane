-- Content subscribers: get notified when new strips / YT shorts are published
CREATE TABLE IF NOT EXISTS content_subscribers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT NOT NULL UNIQUE,
    subscribed_at TIMESTAMPTZ DEFAULT NOW(),
    active BOOLEAN DEFAULT TRUE
);

CREATE INDEX IF NOT EXISTS idx_content_subscribers_active
    ON content_subscribers(active) WHERE active = TRUE;

ALTER TABLE content_subscribers ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Allow anonymous insert" ON content_subscribers
    FOR INSERT WITH CHECK (true);
CREATE POLICY "Service role full access" ON content_subscribers
    FOR ALL USING (auth.role() = 'service_role');
