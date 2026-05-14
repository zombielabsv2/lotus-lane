-- Migration: 004_email_events
-- Resend webhook → email engagement events.
-- Shared across the empire: `app` column distinguishes lotus_lane / astromedha_v3 /
-- kari_growth / mykuber / moonpath. Same Supabase project is used by every sender.

CREATE TABLE IF NOT EXISTS public.email_events (
    id           BIGSERIAL PRIMARY KEY,
    app          TEXT NOT NULL,
    event_type   TEXT NOT NULL,            -- email.sent / delivered / opened / clicked / bounced / complained / delivery_delayed / failed
    message_id   TEXT NOT NULL,            -- resend email_id
    to_email     TEXT,
    from_email   TEXT,
    subject      TEXT,
    click_url    TEXT,                     -- email.clicked only
    user_agent   TEXT,                     -- opened/clicked
    ip_address   TEXT,                     -- opened/clicked
    bounce_type  TEXT,                     -- bounced only
    occurred_at  TIMESTAMPTZ NOT NULL,
    received_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    raw          JSONB NOT NULL
);

CREATE INDEX IF NOT EXISTS email_events_msg_idx
    ON public.email_events(message_id);
CREATE INDEX IF NOT EXISTS email_events_to_idx
    ON public.email_events(to_email);
CREATE INDEX IF NOT EXISTS email_events_app_type_idx
    ON public.email_events(app, event_type, occurred_at DESC);

-- Idempotency: Resend retries on non-2xx, so dedupe at the DB layer.
CREATE UNIQUE INDEX IF NOT EXISTS email_events_dedup_idx
    ON public.email_events(message_id, event_type, occurred_at);

-- Per-message rollup view — what dashboards actually want.
CREATE OR REPLACE VIEW public.email_events_summary AS
SELECT
    message_id,
    MAX(app)        AS app,
    MAX(to_email)   AS to_email,
    MAX(from_email) AS from_email,
    MAX(subject)    AS subject,
    MIN(occurred_at) FILTER (WHERE event_type = 'email.sent')         AS sent_at,
    MIN(occurred_at) FILTER (WHERE event_type = 'email.delivered')    AS delivered_at,
    MIN(occurred_at) FILTER (WHERE event_type = 'email.opened')       AS first_opened_at,
    COUNT(*)         FILTER (WHERE event_type = 'email.opened')       AS open_count,
    MIN(occurred_at) FILTER (WHERE event_type = 'email.clicked')      AS first_clicked_at,
    COUNT(*)         FILTER (WHERE event_type = 'email.clicked')      AS click_count,
    MIN(occurred_at) FILTER (WHERE event_type = 'email.bounced')      AS bounced_at,
    MIN(occurred_at) FILTER (WHERE event_type = 'email.complained')   AS complained_at
FROM public.email_events
GROUP BY message_id;

-- Operator fills this with the `whsec_…` value from the Resend dashboard
-- after creating the webhook endpoint.
INSERT INTO public.pipeline_secrets(key, value)
VALUES ('resend_webhook_secret', '')
ON CONFLICT (key) DO NOTHING;
