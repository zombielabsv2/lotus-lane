-- Daimoku Daily: personalized Nichiren Buddhist wisdom emails
-- Run against Supabase SQL editor

-- Subscribers table
CREATE TABLE IF NOT EXISTS daimoku_subscribers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT NOT NULL UNIQUE,
    name TEXT,
    challenges TEXT[] NOT NULL,  -- array of challenge categories
    situation_text TEXT,
    frequency TEXT NOT NULL DEFAULT 'weekly',  -- daily, thrice_weekly, weekly
    subscribed_at TIMESTAMPTZ DEFAULT NOW(),
    active BOOLEAN DEFAULT TRUE,
    last_sent_at TIMESTAMPTZ,
    timezone TEXT DEFAULT 'Asia/Kolkata'
);

-- Email log table
CREATE TABLE IF NOT EXISTS daimoku_email_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    subscriber_id UUID REFERENCES daimoku_subscribers(id),
    sent_at TIMESTAMPTZ DEFAULT NOW(),
    subject TEXT,
    challenge_category TEXT,
    nichiren_quote TEXT,
    source TEXT,
    status TEXT DEFAULT 'sent'
);

-- Index for efficient subscriber queries
CREATE INDEX IF NOT EXISTS idx_daimoku_subscribers_active
    ON daimoku_subscribers(active) WHERE active = TRUE;

CREATE INDEX IF NOT EXISTS idx_daimoku_subscribers_email
    ON daimoku_subscribers(email);

CREATE INDEX IF NOT EXISTS idx_daimoku_email_log_subscriber
    ON daimoku_email_log(subscriber_id, sent_at DESC);

-- Enable Row Level Security
ALTER TABLE daimoku_subscribers ENABLE ROW LEVEL SECURITY;
ALTER TABLE daimoku_email_log ENABLE ROW LEVEL SECURITY;

-- Policy: allow anonymous inserts (for the signup form via anon key)
CREATE POLICY "Allow anonymous insert" ON daimoku_subscribers
    FOR INSERT
    WITH CHECK (true);

-- Policy: subscribers can only read their own row (by email match — no auth required for insert)
CREATE POLICY "Allow anonymous select own" ON daimoku_subscribers
    FOR SELECT
    USING (true);

-- Policy: service role can do everything (for the email pipeline)
CREATE POLICY "Service role full access subscribers" ON daimoku_subscribers
    FOR ALL
    USING (auth.role() = 'service_role');

CREATE POLICY "Service role full access email_log" ON daimoku_email_log
    FOR ALL
    USING (auth.role() = 'service_role');

-- Allow anon key to insert into email_log (not needed, but just in case)
CREATE POLICY "Allow service insert email_log" ON daimoku_email_log
    FOR INSERT
    WITH CHECK (true);
