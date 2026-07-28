// Kari by Kriti — HTTPS unsubscribe endpoint
//
// Replaces the DECORATIVE link that shipped in every KBK marketing email until
// 2026-07-29: customer_emails.py pointed at
// https://www.karibykriti.com/pages/unsubscribe, a static Shopify page with no
// endpoint behind it. Nothing a customer clicked could write to the suppression
// list (a JSON file in a git repo), so a click had never suppressed anyone —
// on 2026-07-28 all 32 entries in that file were reason='bounce' and not one
// was an unsubscribe, while 17 people had clicked since 15 May.
// anish.basral@hindustanwellness.com unsubscribed 22 May and received six more
// marketing emails through 1 Jul.
//
// Modelled on lotus-lane/supabase/functions/unsubscribe-handler with ONE
// deliberate difference:
//
//   SUPPRESS, NEVER DELETE.
//
// Lotus Lane's unsubscribe hard-deletes the subscriber, which is right for a
// pure newsletter. KBK recipients are Shopify CUSTOMERS with order history —
// erasing them would destroy commercial records. Withdrawing marketing consent
// and deleting a customer are different asks; this endpoint only does the first.
//
// Flow:
//   GET  /kbk-unsubscribe?e=<b64url_email>&t=<hmac_hex>
//     → verify HMAC, upsert into kbk_email_suppressions,
//       302 to https://www.karibykriti.com/pages/unsubscribe?ok=1
//   POST (same URL) → 200 JSON, which is what Gmail's
//       List-Unsubscribe-Post: List-Unsubscribe=One-Click expects (RFC 8058).
//
// Idempotent: an already-suppressed or unknown address still reports success,
// so the endpoint can't be used to enumerate who is on the list.
//
// HMAC key: public.pipeline_secrets row key='kbk_unsubscribe_hmac'. The Python
// sender signs the same way in customer_emails._unsub_link(). Service role only.

import "jsr:@supabase/functions-js/edge-runtime.d.ts";

const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
  "Access-Control-Allow-Headers":
    "authorization, x-client-info, apikey, content-type",
};

const SUCCESS_REDIRECT = "https://www.karibykriti.com/pages/unsubscribe?ok=1";
const HMAC_SECRET_KEY = "kbk_unsubscribe_hmac";

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

  const expected = await hmacSha256Hex(new TextEncoder().encode(secret), email);
  if (!constantTimeEqual(expected, tParam.toLowerCase())) {
    console.warn(`HMAC mismatch for ${email}`);
    return new Response("invalid_signature", { status: 403, headers: CORS });
  }

  // Upsert, never delete. merge-duplicates keeps this idempotent for the
  // repeat clicks that are normal when a mail client prefetches the link.
  const upResp = await fetch(
    `${SUPABASE_URL}/rest/v1/kbk_email_suppressions?on_conflict=email`,
    {
      method: "POST",
      headers: {
        apikey: SERVICE_KEY,
        Authorization: `Bearer ${SERVICE_KEY}`,
        "Content-Type": "application/json",
        Prefer: "resolution=merge-duplicates,return=minimal",
      },
      body: JSON.stringify([{
        email,
        reason: "unsubscribed",
        source: `one_click_${req.method.toLowerCase()}`,
      }]),
    },
  );
  if (!upResp.ok) {
    const detail = await upResp.text();
    console.error("kbk_email_suppressions upsert failed:", upResp.status, detail);
    // Fail LOUD. A silent failure here is exactly the bug this endpoint exists
    // to fix -- the customer must not see a success page for a no-op.
    return new Response("db_error", { status: 500, headers: CORS });
  }

  console.log(`suppressed ${email} via ${req.method}`);

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
