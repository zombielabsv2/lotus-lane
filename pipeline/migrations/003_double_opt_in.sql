-- Double opt-in + bot protection for Daimoku Daily signups
-- Apr 20, 2026 — layered defense against spam bots burning Claude API credits
--
-- Changes:
--   1. Adds confirmation_token + confirmed + confirmed_at + confirmation_sent_at cols
--   2. Existing rows grandfathered confirmed=TRUE (they signed up before this change)
--   3. Revokes anon INSERT — all new signups must flow through edge function gateway
--      (which verifies Cloudflare Turnstile + disposable-domain blocklist)
--   4. Updates dispatch_welcome_email() trigger:
--      - No longer fires on UNCONFIRMED inserts
--      - Fires on INSERT when confirmed=TRUE (grandfathered / admin inserts)
--      - Fires on UPDATE when confirmed flips FALSE->TRUE (via confirm endpoint)
--
-- Idempotent. Safe to re-run.

-- 1. Schema additions --------------------------------------------------------

ALTER TABLE daimoku_subscribers
    ADD COLUMN IF NOT EXISTS confirmed BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS confirmation_token UUID DEFAULT gen_random_uuid(),
    ADD COLUMN IF NOT EXISTS confirmed_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS confirmation_sent_at TIMESTAMPTZ;

-- Grandfather existing subscribers: they're real, they opted in before this change
UPDATE daimoku_subscribers
    SET confirmed = TRUE,
        confirmed_at = COALESCE(confirmed_at, subscribed_at, NOW())
    WHERE confirmed = FALSE AND subscribed_at < NOW() - INTERVAL '1 minute';

-- Index for confirmation-token lookups (hot path in confirm endpoint)
CREATE UNIQUE INDEX IF NOT EXISTS idx_daimoku_subscribers_confirmation_token
    ON daimoku_subscribers(confirmation_token)
    WHERE confirmation_token IS NOT NULL;

-- Index for the common filter: active AND confirmed
CREATE INDEX IF NOT EXISTS idx_daimoku_subscribers_active_confirmed
    ON daimoku_subscribers(active, confirmed) WHERE active = TRUE AND confirmed = TRUE;

-- 2. Lock down anon writes ---------------------------------------------------
-- New signups go through the edge function (service role), NOT direct REST insert

DROP POLICY IF EXISTS "Allow anonymous insert" ON daimoku_subscribers;
DROP POLICY IF EXISTS "Allow anonymous select own" ON daimoku_subscribers;

-- Service role keeps full access (unchanged, but declared here for idempotency)
DROP POLICY IF EXISTS "Service role full access subscribers" ON daimoku_subscribers;
CREATE POLICY "Service role full access subscribers" ON daimoku_subscribers
    FOR ALL USING (auth.role() = 'service_role');

-- 3. Trigger: gate on confirmed ---------------------------------------------

CREATE OR REPLACE FUNCTION public.dispatch_welcome_email()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
AS $function$
DECLARE
  gh_token text;
  should_fire boolean := FALSE;
BEGIN
  -- Skip if no email or row is inactive
  IF NEW.email IS NULL OR NEW.active IS DISTINCT FROM TRUE THEN
    RETURN NEW;
  END IF;

  -- Only fire when the row is confirmed:
  --   INSERT + confirmed=true  -> grandfathered/admin inserts
  --   UPDATE + confirmed flipped false->true -> user clicked confirm link
  IF TG_OP = 'INSERT' AND NEW.confirmed = TRUE THEN
    should_fire := TRUE;
  ELSIF TG_OP = 'UPDATE'
        AND NEW.confirmed = TRUE
        AND OLD.confirmed IS DISTINCT FROM TRUE THEN
    should_fire := TRUE;
  END IF;

  IF NOT should_fire THEN
    RETURN NEW;
  END IF;

  SELECT decrypted_secret INTO gh_token
    FROM vault.decrypted_secrets
    WHERE name = 'lotus_lane_gh_dispatch_token'
    LIMIT 1;

  IF gh_token IS NULL THEN
    RAISE WARNING 'lotus_lane_gh_dispatch_token not set in vault; skipping dispatch';
    RETURN NEW;
  END IF;

  PERFORM net.http_post(
    url := 'https://api.github.com/repos/zombielabsv2/lotus-lane/dispatches',
    headers := jsonb_build_object(
      'Accept', 'application/vnd.github+json',
      'Authorization', 'Bearer ' || gh_token,
      'X-GitHub-Api-Version', '2022-11-28',
      'User-Agent', 'supabase-lotus-lane-trigger',
      'Content-Type', 'application/json'
    ),
    body := jsonb_build_object(
      'event_type', 'new_subscriber',
      'client_payload', jsonb_build_object('email', NEW.email)
    )
  );

  RETURN NEW;
END;
$function$;

-- Replace trigger: INSERT OR UPDATE OF confirmed
DROP TRIGGER IF EXISTS dispatch_welcome_email_trg ON daimoku_subscribers;
CREATE TRIGGER dispatch_welcome_email_trg
    AFTER INSERT OR UPDATE OF confirmed ON daimoku_subscribers
    FOR EACH ROW
    EXECUTE FUNCTION dispatch_welcome_email();
