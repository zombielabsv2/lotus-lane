// Daimoku Daily — signup gateway
//
// Flow:
//   1. Browser submits form + Cloudflare Turnstile token
//   2. We verify Turnstile -> reject bots
//   3. Reject disposable/throwaway email domains
//   4. Insert row with confirmed=FALSE and fresh UUID confirmation_token
//   5. Send confirmation email via Resend with link to thelotuslane.in/confirm.html?token=...
//
// The Postgres trigger dispatch_welcome_email_trg does NOT fire on this insert
// (gated on confirmed=true). It only fires once the user clicks the confirm link.

import "jsr:@supabase/functions-js/edge-runtime.d.ts";

const CONFIRM_URL_BASE = "https://thelotuslane.in/confirm.html";
const MAX_CHALLENGES = 3;
const VALID_FREQUENCIES = new Set(["daily", "thrice_weekly", "weekly"]);
// Signup bucket keys — kept narrow 1:1 with a /wisdom/ article so the confirm
// CTA and welcome-email routing never show the wrong page. Legacy broad keys
// (career/health/relationships/family/finances/self-doubt/perseverance) were
// retired from signup Apr 2026; existing subscribers still carry them and the
// email pipeline resolves them via fallback maps.
const VALID_CHALLENGES = new Set([
  "burnout", "toxic-workplace", "sidelined", "imposter",
  "relationship-conflict", "divorce",
  "parenting", "caregiving", "forgiveness",
  "money",
  "chronic-illness", "depression", "anxiety",
  "grief", "loneliness", "starting-over",
]);

// Disposable / throwaway email domains. Not exhaustive — just the common ones.
// Compound layer with Turnstile; if bots slip past Turnstile, this catches the
// obvious throwaways.
const DISPOSABLE_DOMAINS = new Set([
  "mailinator.com", "tempmail.com", "10minutemail.com", "guerrillamail.com",
  "guerrillamail.net", "guerrillamail.org", "sharklasers.com",
  "yopmail.com", "throwaway.email", "trashmail.com", "getnada.com",
  "maildrop.cc", "mohmal.com", "temp-mail.org", "fakeinbox.com",
  "dispostable.com", "mailnesia.com", "spambog.com", "tempr.email",
  "emailondeck.com", "mytemp.email", "mailcatch.com", "mintemail.com",
  "mvrht.net", "inboxbear.com", "dropmail.me", "spam4.me",
  "harakirimail.com", "mailnull.com", "trbvn.com", "mail-temp.com",
]);

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

function isValidEmail(email: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email) && email.length <= 254;
}

function domainOf(email: string): string {
  return email.split("@")[1]?.toLowerCase() ?? "";
}

async function verifyTurnstile(token: string, remoteIp: string | null): Promise<boolean> {
  const secret = Deno.env.get("TURNSTILE_SECRET_KEY");
  if (!secret) {
    console.error("TURNSTILE_SECRET_KEY not configured");
    return false;
  }
  const form = new FormData();
  form.append("secret", secret);
  form.append("response", token);
  if (remoteIp) form.append("remoteip", remoteIp);

  try {
    const resp = await fetch(
      "https://challenges.cloudflare.com/turnstile/v0/siteverify",
      { method: "POST", body: form },
    );
    const data = await resp.json();
    if (!data.success) {
      console.log("Turnstile reject:", data["error-codes"]);
    }
    return data.success === true;
  } catch (e) {
    console.error("Turnstile verify error:", e);
    return false;
  }
}

function buildConfirmationEmail(name: string, token: string): { subject: string; html: string } {
  const confirmLink = `${CONFIRM_URL_BASE}?token=${token}`;
  const safeName = name.replace(/[<>&"]/g, "");
  return {
    subject: "Confirm your Daily Lotus subscription",
    html: `<!DOCTYPE html>
<html><body style="margin:0;padding:0;background:#faf9f6;font-family:-apple-system,Segoe UI,sans-serif;color:#2d2d2d;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#faf9f6;padding:24px 0;">
    <tr><td align="center">
      <table width="560" cellpadding="0" cellspacing="0" style="background:#fff;border-radius:12px;padding:32px;box-shadow:0 2px 20px rgba(0,0,0,.06);">
        <tr><td>
          <h1 style="margin:0 0 12px;font-size:22px;font-weight:300;letter-spacing:.1em;color:#4a4a4a;">The <span style="color:#c0392b;font-weight:600;">Lotus</span> Lane</h1>
          <p style="margin:0 0 20px;font-size:15px;line-height:1.6;color:#555;">Hi ${safeName},</p>
          <p style="margin:0 0 20px;font-size:15px;line-height:1.6;color:#555;">One tap to confirm and we'll start sending wisdom for what you're going through.</p>
          <p style="margin:28px 0;text-align:center;">
            <a href="${confirmLink}" style="display:inline-block;padding:14px 32px;background:#c0392b;color:#fff;text-decoration:none;border-radius:8px;font-weight:600;font-size:15px;">Confirm my subscription</a>
          </p>
          <p style="margin:20px 0 0;font-size:13px;line-height:1.6;color:#999;">Or paste this link into your browser:<br><span style="color:#777;word-break:break-all;">${confirmLink}</span></p>
          <hr style="border:none;border-top:1px solid #eee;margin:28px 0 16px;">
          <p style="margin:0;font-size:12px;line-height:1.5;color:#aaa;">If you didn't ask for this, you can ignore this email — we won't send anything unless you confirm.</p>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body></html>`,
  };
}

Deno.serve(async (req: Request) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: corsHeaders });
  if (req.method !== "POST") return json(405, { error: "method_not_allowed" });

  const SUPABASE_URL = Deno.env.get("SUPABASE_URL") ?? "";
  const SERVICE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") ?? "";
  const RESEND_API_KEY = Deno.env.get("RESEND_API_KEY") ?? "";
  if (!SUPABASE_URL || !SERVICE_KEY || !RESEND_API_KEY) {
    console.error("Missing env: SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY/RESEND_API_KEY");
    return json(500, { error: "server_misconfigured" });
  }

  let body: Record<string, unknown>;
  try {
    body = await req.json();
  } catch {
    return json(400, { error: "invalid_json" });
  }

  const turnstileToken = String(body.turnstileToken ?? "").trim();
  const email = String(body.email ?? "").trim().toLowerCase();
  const name = String(body.name ?? "").trim().slice(0, 80);
  const situation = String(body.situation ?? "").trim().slice(0, 2000);
  const frequency = String(body.frequency ?? "weekly");
  const challengesRaw = Array.isArray(body.challenges) ? body.challenges : [];

  // --- Input validation -----------------------------------------------------
  if (!turnstileToken) return json(400, { error: "turnstile_required" });
  if (!name) return json(400, { error: "name_required" });
  if (!email || !isValidEmail(email)) return json(400, { error: "invalid_email" });
  if (!VALID_FREQUENCIES.has(frequency)) return json(400, { error: "invalid_frequency" });

  const challenges = challengesRaw
    .map((c) => String(c).trim().toLowerCase())
    .filter((c) => VALID_CHALLENGES.has(c))
    .slice(0, MAX_CHALLENGES);
  if (challenges.length === 0) return json(400, { error: "pick_at_least_one_challenge" });

  if (DISPOSABLE_DOMAINS.has(domainOf(email))) {
    return json(400, { error: "disposable_email_not_allowed" });
  }

  // --- Turnstile verification ----------------------------------------------
  const remoteIp = req.headers.get("cf-connecting-ip") ?? req.headers.get("x-real-ip");
  const turnstileOk = await verifyTurnstile(turnstileToken, remoteIp);
  if (!turnstileOk) return json(400, { error: "bot_check_failed" });

  // --- Insert / upsert pending subscriber ----------------------------------
  // If the email already exists:
  //   - confirmed=TRUE -> tell them they're already subscribed
  //   - confirmed=FALSE -> re-send the confirmation email (rotate the token)
  const existingResp = await fetch(
    `${SUPABASE_URL}/rest/v1/daimoku_subscribers?email=eq.${encodeURIComponent(email)}&select=id,confirmed,confirmation_token`,
    { headers: { apikey: SERVICE_KEY, Authorization: `Bearer ${SERVICE_KEY}` } },
  );
  const existing = existingResp.ok ? await existingResp.json() : [];

  let confirmationToken: string;
  if (existing.length > 0) {
    const row = existing[0];
    if (row.confirmed) {
      return json(409, { error: "already_subscribed" });
    }
    confirmationToken = crypto.randomUUID();
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
          name,
          challenges,
          situation_text: situation || null,
          frequency,
          confirmation_token: confirmationToken,
          confirmation_sent_at: new Date().toISOString(),
        }),
      },
    );
    if (!patchResp.ok) {
      console.error("Patch failed:", patchResp.status, await patchResp.text());
      return json(500, { error: "db_error" });
    }
  } else {
    confirmationToken = crypto.randomUUID();
    const insertResp = await fetch(
      `${SUPABASE_URL}/rest/v1/daimoku_subscribers`,
      {
        method: "POST",
        headers: {
          apikey: SERVICE_KEY,
          Authorization: `Bearer ${SERVICE_KEY}`,
          "Content-Type": "application/json",
          Prefer: "return=minimal",
        },
        body: JSON.stringify({
          email,
          name,
          challenges,
          situation_text: situation || null,
          frequency,
          confirmed: false,
          confirmation_token: confirmationToken,
          confirmation_sent_at: new Date().toISOString(),
        }),
      },
    );
    if (!insertResp.ok) {
      console.error("Insert failed:", insertResp.status, await insertResp.text());
      return json(500, { error: "db_error" });
    }
  }

  // --- Send confirmation email via Resend ----------------------------------
  const { subject, html } = buildConfirmationEmail(name, confirmationToken);
  const resendResp = await fetch("https://api.resend.com/emails", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${RESEND_API_KEY}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      from: "Daily Wisdom <daimoku@rxjapps.in>",
      to: [email],
      subject,
      html,
    }),
  });
  if (!resendResp.ok) {
    console.error("Resend failed:", resendResp.status, await resendResp.text());
    return json(500, { error: "email_send_failed" });
  }

  return json(200, { ok: true, status: "confirmation_sent" });
});
