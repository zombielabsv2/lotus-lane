// Resend → email_events sink.
//
// Verifies the Svix signature on each Resend webhook and inserts one row per
// event into public.email_events. Shared across every empire app that sends
// via Resend — `app` is derived from the From-address domain. Add new senders
// to DOMAIN_TO_APP as they come online.
//
// Resend reference:
//   - Signing: https://resend.com/docs/dashboard/webhooks/verify-webhooks-requests
//     Headers: svix-id, svix-timestamp, svix-signature ("v1,<base64> v1,<base64>")
//     Signed payload: `${svix_id}.${svix_timestamp}.${body}`
//     Secret: "whsec_<base64>" — strip prefix, base64-decode, HMAC-SHA-256
//
// Event types: email.sent, .delivered, .delivery_delayed, .complained,
//              .bounced, .opened, .clicked, .failed
//
// Dedup is enforced by the (message_id, event_type, occurred_at) unique index;
// a duplicate insert yields 409 which we treat as success.

import "jsr:@supabase/functions-js/edge-runtime.d.ts";

const SECRET_KEY = "resend_webhook_secret";
const SIGNATURE_TOLERANCE_SECONDS = 5 * 60;

const DOMAIN_TO_APP: Record<string, string> = {
  "thelotuslane.in": "lotus_lane",
  "astromedha.in":   "astromedha_v3",
  "karibykriti.com": "kari_growth",
  "mykuber.in":      "mykuber",
  "moonpath.in":     "moonpath",
  "rxjapps.in":      "rxjapps",
};

function appFromAddress(fromValue: unknown): string {
  if (typeof fromValue !== "string") return "unknown";
  const match = fromValue.match(/<?([^<>\s]+@[^<>\s]+)>?/);
  if (!match) return "unknown";
  const domain = match[1].split("@")[1].toLowerCase();
  return DOMAIN_TO_APP[domain] ?? domain.split(".")[0];
}

function base64Decode(s: string): Uint8Array {
  return Uint8Array.from(atob(s), (c) => c.charCodeAt(0));
}

function constantTimeEqual(a: Uint8Array, b: Uint8Array): boolean {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a[i] ^ b[i];
  return diff === 0;
}

async function importHmacKey(secret: string): Promise<CryptoKey> {
  const raw = secret.startsWith("whsec_") ? secret.slice(6) : secret;
  return crypto.subtle.importKey(
    "raw",
    base64Decode(raw),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
}

async function verifySvixSignature(
  key: CryptoKey,
  svixId: string,
  svixTimestamp: string,
  body: string,
  signatureHeader: string,
): Promise<boolean> {
  const ts = Number(svixTimestamp);
  if (!Number.isFinite(ts)) return false;
  const nowSec = Math.floor(Date.now() / 1000);
  if (Math.abs(nowSec - ts) > SIGNATURE_TOLERANCE_SECONDS) return false;

  const signed = `${svixId}.${svixTimestamp}.${body}`;
  const expected = new Uint8Array(
    await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(signed)),
  );

  for (const part of signatureHeader.split(/\s+/)) {
    const [version, b64] = part.split(",");
    if (version !== "v1" || !b64) continue;
    try {
      if (constantTimeEqual(base64Decode(b64), expected)) return true;
    } catch {
      // bad base64 — try next
    }
  }
  return false;
}

let cachedSecret: string | null = null;
async function loadWebhookSecret(
  supabaseUrl: string,
  serviceKey: string,
): Promise<string> {
  if (cachedSecret) return cachedSecret;
  const resp = await fetch(
    `${supabaseUrl}/rest/v1/pipeline_secrets?key=eq.${SECRET_KEY}&select=value`,
    { headers: { apikey: serviceKey, Authorization: `Bearer ${serviceKey}` } },
  );
  if (!resp.ok) throw new Error(`secret_fetch_failed_${resp.status}`);
  const rows = await resp.json();
  if (!Array.isArray(rows) || rows.length === 0 || !rows[0].value) {
    throw new Error("secret_row_missing_or_empty");
  }
  cachedSecret = String(rows[0].value);
  return cachedSecret;
}

Deno.serve(async (req: Request) => {
  if (req.method !== "POST") {
    return new Response("method_not_allowed", { status: 405 });
  }

  const SUPABASE_URL = Deno.env.get("SUPABASE_URL") ?? "";
  const SERVICE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") ?? "";
  if (!SUPABASE_URL || !SERVICE_KEY) {
    console.error("Missing env: SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY");
    return new Response("server_misconfigured", { status: 500 });
  }

  const svixId = req.headers.get("svix-id");
  const svixTs = req.headers.get("svix-timestamp");
  const svixSig = req.headers.get("svix-signature");
  if (!svixId || !svixTs || !svixSig) {
    return new Response("missing_svix_headers", { status: 400 });
  }

  const body = await req.text();

  let secret: string;
  try {
    secret = await loadWebhookSecret(SUPABASE_URL, SERVICE_KEY);
  } catch (e) {
    console.error("secret load failed:", e);
    return new Response("secret_unavailable", { status: 500 });
  }

  const key = await importHmacKey(secret);
  const valid = await verifySvixSignature(key, svixId, svixTs, body, svixSig);
  if (!valid) {
    console.warn("svix signature invalid", { svixId, svixTs });
    return new Response("invalid_signature", { status: 403 });
  }

  let payload: Record<string, unknown>;
  try {
    payload = JSON.parse(body);
  } catch {
    return new Response("bad_json", { status: 400 });
  }

  const eventType = String(payload?.type ?? "unknown");
  const data = (payload?.data ?? {}) as Record<string, unknown>;
  const createdAt = String(
    payload?.created_at ?? data?.created_at ?? new Date().toISOString(),
  );

  const click = (data?.click ?? {}) as Record<string, unknown>;
  const open = (data?.open ?? {}) as Record<string, unknown>;
  const bounce = (data?.bounce ?? {}) as Record<string, unknown>;
  const toField = data?.to;

  const row = {
    app: appFromAddress(data?.from),
    event_type: eventType,
    message_id: String(data?.email_id ?? data?.id ?? svixId),
    to_email: Array.isArray(toField) ? String(toField[0] ?? "") : (toField as string | null) ?? null,
    from_email: (data?.from as string | null) ?? null,
    subject: (data?.subject as string | null) ?? null,
    click_url: (click?.link as string | null) ?? null,
    user_agent: (click?.userAgent ?? open?.userAgent ?? null) as string | null,
    ip_address: (click?.ipAddress ?? open?.ipAddress ?? null) as string | null,
    bounce_type: (bounce?.subType ?? bounce?.type ?? null) as string | null,
    occurred_at: createdAt,
    raw: payload,
  };

  const insertResp = await fetch(`${SUPABASE_URL}/rest/v1/email_events`, {
    method: "POST",
    headers: {
      apikey: SERVICE_KEY,
      Authorization: `Bearer ${SERVICE_KEY}`,
      "Content-Type": "application/json",
      Prefer: "return=minimal",
    },
    body: JSON.stringify(row),
  });

  // 409 = duplicate (dedup index) — treat as success so Resend doesn't retry.
  if (!insertResp.ok && insertResp.status !== 409) {
    const errText = await insertResp.text();
    console.error("email_events insert failed:", insertResp.status, errText);
    return new Response("db_error", { status: 500 });
  }

  return new Response(JSON.stringify({ ok: true }), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
});
