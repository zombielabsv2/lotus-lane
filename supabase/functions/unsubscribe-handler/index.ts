// The Lotus Lane — HTTPS unsubscribe endpoint
//
// Replaces the broken mailto:unsubscribe@rxjapps.in link that bounced
// (550 Address does not exist) on 2026-04-23. Compatible with Gmail's
// one-click List-Unsubscribe-Post: List-Unsubscribe=One-Click.
//
// Flow:
//   GET  /unsubscribe-handler?e=<b64url_email>&t=<hmac_hex>
//     → verify HMAC, flip daimoku_subscribers.active=false,
//       redirect 302 to https://thelotuslane.in/unsubscribe.html?ok=1
//   POST (same URL) → 200 JSON (what Gmail one-click expects)
//
// Idempotent: already-inactive and unknown emails still return success
// (no enumeration leak).
//
// HMAC key source: public.pipeline_secrets row with key='lotus_lane_unsubscribe_hmac'.
// Same row is read on the Python sender side via PostgREST. Service role only.

import "jsr:@supabase/functions-js/edge-runtime.d.ts";

const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
  "Access-Control-Allow-Headers":
    "authorization, x-client-info, apikey, content-type",
};

const SUCCESS_REDIRECT = "https://thelotuslane.in/unsubscribe.html?ok=1";
const HMAC_SECRET_KEY = "lotus_lane_unsubscribe_hmac";

let cachedSecret: string | null = null;

function base64urlDecode(s: string): string {
  const pad = s.length % 4 === 0 ? "" : "=".repeat(4 - (s.length % 4));
  const b64 = (s + pad).replace(/-/g, "+").replace(/_/g, "/");
  return atob(b64);
}

function hexFromBuffer(buf: ArrayBuffer): string {
  return Array.from(new Uint8Array(buf))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

async function hmacSha256Hex(keyBytes: Uint8Array, msg: string): Promise<string> {
  const key = await crypto.subtle.importKey(
    "raw",
    keyBytes,
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const sig = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(msg));
  return hexFromBuffer(sig);
}

function constantTimeEqual(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

async function loadHmacSecret(
  supabaseUrl: string,
  serviceKey: string,
): Promise<string> {
  if (cachedSecret) return cachedSecret;
  const resp = await fetch(
    `${supabaseUrl}/rest/v1/pipeline_secrets?key=eq.${HMAC_SECRET_KEY}&select=value`,
    { headers: { apikey: serviceKey, Authorization: `Bearer ${serviceKey}` } },
  );
  if (!resp.ok) throw new Error(`secret_fetch_failed_${resp.status}`);
  const rows = await resp.json();
  if (!Array.isArray(rows) || rows.length === 0) {
    throw new Error("secret_row_missing");
  }
  cachedSecret = String(rows[0].value);
  return cachedSecret;
}

Deno.serve(async (req: Request) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: CORS });
  if (req.method !== "GET" && req.method !== "POST") {
    return new Response("method_not_allowed", { status: 405, headers: CORS });
  }

  const SUPABASE_URL = Deno.env.get("SUPABASE_URL") ?? "";
  const SERVICE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") ?? "";
  if (!SUPABASE_URL || !SERVICE_KEY) {
    console.error("Missing env: SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY");
    return new Response("server_misconfigured", { status: 500, headers: CORS });
  }

  const url = new URL(req.url);
  const eParam = url.searchParams.get("e") ?? "";
  const tParam = url.searchParams.get("t") ?? "";
  if (!eParam || !tParam) {
    return new Response("missing_params", { status: 400, headers: CORS });
  }

  let email: string;
  try {
    email = base64urlDecode(eParam).toLowerCase().trim();
  } catch {
    return new Response("bad_email_encoding", { status: 400, headers: CORS });
  }
  if (!email.includes("@")) {
    return new Response("bad_email", { status: 400, headers: CORS });
  }

  let secret: string;
  try {
    secret = await loadHmacSecret(SUPABASE_URL, SERVICE_KEY);
  } catch (e) {
    console.error("Secret load failed:", e);
    return new Response("secret_unavailable", { status: 500, headers: CORS });
  }

  const expected = await hmacSha256Hex(
    new TextEncoder().encode(secret),
    email,
  );
  if (!constantTimeEqual(expected, tParam.toLowerCase())) {
    console.warn(`HMAC mismatch for ${email}`);
    return new Response("invalid_signature", { status: 403, headers: CORS });
  }

  const patchResp = await fetch(
    `${SUPABASE_URL}/rest/v1/daimoku_subscribers?email=eq.${encodeURIComponent(email)}`,
    {
      method: "PATCH",
      headers: {
        apikey: SERVICE_KEY,
        Authorization: `Bearer ${SERVICE_KEY}`,
        "Content-Type": "application/json",
        Prefer: "return=minimal",
      },
      body: JSON.stringify({ active: false }),
    },
  );
  if (!patchResp.ok) {
    console.error("daimoku_subscribers PATCH failed:", patchResp.status, await patchResp.text());
    return new Response("db_error", { status: 500, headers: CORS });
  }

  // Also flag content_subscribers if present (older new-strip notification list)
  try {
    await fetch(
      `${SUPABASE_URL}/rest/v1/content_subscribers?email=eq.${encodeURIComponent(email)}`,
      {
        method: "PATCH",
        headers: {
          apikey: SERVICE_KEY,
          Authorization: `Bearer ${SERVICE_KEY}`,
          "Content-Type": "application/json",
          Prefer: "return=minimal",
        },
        body: JSON.stringify({ active: false }),
      },
    );
  } catch (_) {
    // non-fatal
  }

  if (req.method === "POST") {
    return new Response(JSON.stringify({ ok: true }), {
      status: 200,
      headers: { ...CORS, "Content-Type": "application/json" },
    });
  }

  return new Response(null, {
    status: 302,
    headers: { ...CORS, Location: SUCCESS_REDIRECT },
  });
});
