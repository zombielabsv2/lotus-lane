// Daimoku Daily — confirmation endpoint
//
// Flow:
//   1. User clicks link in confirmation email: /confirm.html?token=UUID
//   2. confirm.html POSTs the token here
//   3. We look up the row by confirmation_token
//   4. Flip confirmed=TRUE + confirmed_at=now() + null out the token (one-shot)
//   5. Postgres trigger dispatch_welcome_email_trg fires on UPDATE OF confirmed,
//      which kicks off the welcome-new-subscriber.yml workflow. We do NOT
//      trigger repository_dispatch from here — the DB trigger handles it.
//
// Idempotent-ish: if the token was already consumed, we report a friendly
// "already confirmed" instead of "not found" when we can still match by email.

import "jsr:@supabase/functions-js/edge-runtime.d.ts";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
};

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { ...corsHeaders, "Content-Type": "application/json" },
  });
}

function isUuid(s: string): boolean {
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(s);
}

Deno.serve(async (req: Request) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: corsHeaders });
  if (req.method !== "POST") return json(405, { error: "method_not_allowed" });

  const SUPABASE_URL = Deno.env.get("SUPABASE_URL") ?? "";
  const SERVICE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") ?? "";
  if (!SUPABASE_URL || !SERVICE_KEY) {
    console.error("Missing env: SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY");
    return json(500, { error: "server_misconfigured" });
  }

  let body: Record<string, unknown>;
  try {
    body = await req.json();
  } catch {
    return json(400, { error: "invalid_json" });
  }

  const token = String(body.token ?? "").trim();
  if (!isUuid(token)) return json(400, { error: "invalid_token" });

  // Look up by token
  const lookupResp = await fetch(
    `${SUPABASE_URL}/rest/v1/daimoku_subscribers?confirmation_token=eq.${token}&select=id,name,email,confirmed`,
    { headers: { apikey: SERVICE_KEY, Authorization: `Bearer ${SERVICE_KEY}` } },
  );
  if (!lookupResp.ok) {
    console.error("Lookup failed:", lookupResp.status, await lookupResp.text());
    return json(500, { error: "db_error" });
  }
  const rows = await lookupResp.json();
  if (!Array.isArray(rows) || rows.length === 0) {
    return json(404, { error: "token_not_found_or_already_used" });
  }

  const row = rows[0];
  if (row.confirmed) {
    return json(200, { ok: true, status: "already_confirmed", name: row.name ?? "" });
  }

  // Flip confirmed=TRUE + null the token so the link can't be reused.
  const patchResp = await fetch(
    `${SUPABASE_URL}/rest/v1/daimoku_subscribers?id=eq.${row.id}`,
    {
      method: "PATCH",
      headers: {
        apikey: SERVICE_KEY,
        Authorization: `Bearer ${SERVICE_KEY}`,
        "Content-Type": "application/json",
        Prefer: "return=minimal",
      },
      body: JSON.stringify({
        confirmed: true,
        confirmed_at: new Date().toISOString(),
        confirmation_token: null,
      }),
    },
  );
  if (!patchResp.ok) {
    console.error("Confirm patch failed:", patchResp.status, await patchResp.text());
    return json(500, { error: "db_error" });
  }

  return json(200, { ok: true, status: "confirmed", name: row.name ?? "" });
});
