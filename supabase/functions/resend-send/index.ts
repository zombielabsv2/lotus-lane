// resend-send — the empire's single email chokepoint.
//
// WHY THIS EXISTS
// Rahul, 2026-07-14: "every email across the empire needs to be mobile friendly -
// that is just hygiene in 2026." An audit of what we ACTUALLY delivered (pulled
// back from Resend, not read from code) found 110 of 113 live email types clipping
// on a phone — including customer emails ("Care tips for your block print sleeve,
// Ishika!", "your free reading is ready"). Same bug re-created independently in
// every repo, because every sender hand-rolls its own HTML.
//
// Fixing it per-repo means two implementations (Python + TypeScript) and N repos
// to keep in sync — and a NEW repo silently opts out. So instead every app POSTs
// here instead of at api.resend.com. This applies the mobile fix and forwards.
// One place. A new app gets it for free.
//
// ROOT CAUSE it fixes: a missing <meta viewport> makes a mobile webview lay the
// email out on a ~980px canvas and clip it on a 375px screen, with no horizontal
// scroll. Verified on delivered HTML: 980px -> 375px after the fix.
//
// CONTRACT: byte-for-byte the Resend API. Same paths, same JSON body, same
// Authorization header (forwarded as-is — this function never holds the API key).
// Callers change ONE thing: the base URL. Response is passed through verbatim.
//
// FAIL-OPEN: this sits in the send path, so a bug here must never drop an email.
// Any error in the transform => forward the ORIGINAL body unchanged. An email
// that clips is bad; an email that never arrives is worse.
//
// !! NEVER let a find-and-replace rewrite RESEND_API to this function's own URL.
// !! That makes the proxy call itself in an infinite loop. (Nearly shipped exactly
// !! that on 2026-07-14 with a blanket s/api.resend.com/proxy/ across all repos.)
//
// ---------------------------------------------------------------------------
// FLOOD GUARD (added 2026-08-04) — the second reason this function exists.
//
// On 2026-08-03/04 an AstroMedha drip bug re-sent the welcome email once per
// Chart Chat turn. One paying customer received 79 copies of the same email in
// 16 hours and tried to delete her account. Engagement was the amplifier: the
// more someone used the product, the more mail we sent them. Nothing noticed
// for 16 hours, because every guard in that path was advisory, in-process, and
// upstream of here.
//
// The senders cannot be trusted to guard themselves — there are 32 call sites
// across 20 files POSTing here directly, and a new one opts out by default.
// This is the only place every app already passes through, so this is where a
// volume bound actually holds.
//
// Two bounds, both backed by a Postgres primary key (exact, race-free):
//   * duplicate — same recipient + same subject + same body, same UTC day.
//     Applied to EVERY app. Identical content twice in a day is never intended.
//   * daily_cap — a per-recipient ceiling, applied ONLY to apps whose real
//     sending baseline has been measured. astromedha = 18 (measured over 5,610
//     recipient-days with the storm excluded: mean 1.32, p95 2, p99 4, max 9;
//     ceiling is 2x observed max). Every other app is dedup-only until its
//     baseline is measured — an unmeasured round-number ceiling on someone
//     else's business is how you cry wolf and get ignored.
//
// FAIL-OPEN IS PRESERVED, with one deliberate exception. If the guard cannot be
// reached (Supabase down, RPC slow, anything unexpected) we SEND — the original
// principle stands, infrastructure trouble must never cost an email. We refuse
// only on an affirmative verdict from the database: it looked, and it says this
// is a duplicate or over the ceiling. Error => send. Proven flood => refuse.
// ---------------------------------------------------------------------------

const RESEND_API = "https://api.resend.com";
const PHONE_SAFE_PX = 360; // narrowest common phone (iPhone SE) is ~320; 360 is the safe ceiling

const VIEWPORT_META =
  '<meta name="viewport" content="width=device-width, initial-scale=1">';

const MOBILE_STYLE = `<style>
  body { -webkit-text-size-adjust: 100%; margin: 0; }
  img { max-width: 100%; height: auto; }
  table { max-width: 100%; }
  /* Break a genuinely unbreakable 180-char tracking URL so it can't widen the
     body. Use the GENTLE break rule below, never the aggressive one: the
     aggressive rules also shrink a cell's MIN-CONTENT width to ~1 char, so a
     text column in a roster/scorecard collapses and its content shatters one
     glyph per line ("rxj@google.com" -> a vertical stack of letters; a number
     like "Rs 33,083" -> "Rs 33,0 / 83"). The gentle rule still breaks a truly
     unbreakable long token, but leaves normal words and numbers whole. This is
     the exact fix the Python twin (kari-growth-platform/utils/email_mobile.py)
     landed 2026-07-19; it was never propagated here, so the central layer kept
     shattering every multi-word cell across all 113 email types — the Lotus
     Lane roster and daily brief Rahul kept screenshotting. Propagated
     2026-07-20. Do NOT reintroduce the aggressive break rules here. */
  p, td, th, a, li, div { overflow-wrap: break-word; }
  .kbk-scroll { overflow-x: auto; -webkit-overflow-scrolling: touch; }
  @media only screen and (max-width: 480px) {
    .kbk-fluid { width: 100% !important; max-width: 100% !important; }
    td, th { font-size: 13px !important; }
  }
</style>`;

// The lookbehinds matter: without them this also matches the "width:640px" INSIDE
// "max-width:640px" — i.e. it rewrites its own output and stops being idempotent.
const INLINE_WIDTH = /(?<!max-)(?<!min-)width\s*:\s*(\d{3,})px/gi;

export function mobileSafe(html: string): string {
  if (!html || typeof html !== "string") return html;

  // Fixed widths -> fluid (fits a phone, unchanged on desktop).
  let out = html.replace(INLINE_WIDTH, (m, px) =>
    Number(px) > PHONE_SAFE_PX ? `width:100%;max-width:${px}px` : m
  );

  // min-width pins the layout wider than the screen — nothing can shrink it.
  out = out.replace(/min-width\s*:\s*(\d{3,})px/gi, (m, px) =>
    Number(px) > PHONE_SAFE_PX ? "min-width:0" : m
  );

  // Legacy width attributes: <table width="600"> -> fluid with a max-width.
  // The max-width is MERGED into any style the tag already carries. Emitting a
  // second style="..." looks harmless and is not: HTML parsers keep the FIRST
  // occurrence of a duplicate attribute and discard the rest, so the tag's real
  // styling (background, border, width) silently vanished while the injected
  // max-width won. Caught on the 2026-07-26 KBK briefing, whose shell table had
  // both width="640" and inline styles and so lost its white card in Gmail.
  // Mirrors the Python twin's _merge_max_width (utils/email_mobile.py).
  out = out.replace(
    /<(table|td|th|img)([^>]*?)\swidth=["']?(\d{3,})["']?([^>]*?)>/gi,
    (m, tag, pre, px, post) => {
      if (Number(px) <= PHONE_SAFE_PX) return m;
      const attrs = `${pre}${post}`;
      const style = /\sstyle=(["'])([\s\S]*?)\1/i.exec(attrs);
      // No type annotation here on purpose: tests/test_resend_send_mobile_safe.py
      // runs this function body through plain node, which cannot parse TS syntax.
      let merged;
      if (!style) {
        merged = `${attrs} style="max-width:${px}px"`;
      } else if (/max-width\s*:/i.test(style[2])) {
        merged = attrs; // already capped, leave it alone
      } else {
        const sep = !style[2].trim() || style[2].trimEnd().endsWith(";") ? "" : ";";
        const value = `${style[2]}${sep}max-width:${px}px`;
        merged =
          attrs.slice(0, style.index) +
          ` style=${style[1]}${value}${style[1]}` +
          attrs.slice(style.index + style[0].length);
      }
      return `<${tag} width="100%"${merged}>`;
    }
  );

  // Wide DATA tables (>=4 cells in the first row) scroll inside their own box.
  // Layout tables — the 1-2 cell nesting email templates use for structure — are
  // left alone; wrapping those breaks the layout without fixing anything.
  // Idempotency: check the 60 chars BEFORE the table for an existing wrapper —
  // the wrapper div is not part of the <table>..</table> block, so checking the
  // block itself never sees it and re-wraps on every pass (and double-wraps an
  // email a Python-side mobile_safe() already wrapped). Mirrors the Python twin.
  out = out.replace(/[\s\S]{0,60}?<table\b[\s\S]*?<\/table>/gi, (chunk) => {
    const tableStart = chunk.search(/<table\b/i);
    const before = chunk.slice(0, tableStart);
    const block = chunk.slice(tableStart);
    const firstRow = block.match(/<tr\b[\s\S]*?<\/tr>/i);
    const cells = firstRow ? (firstRow[0].match(/<t[dh]\b/gi) || []).length : 0;
    if (cells >= 4 && !before.includes("kbk-scroll")) {
      return `${before}<div class="kbk-scroll">${block}</div>`;
    }
    return chunk;
  });

  // THE ACTUAL BUG: without this, a phone lays the email out at ~980px and clips.
  if (!/name=["']viewport/i.test(out)) {
    if (/<head[^>]*>/i.test(out)) {
      out = out.replace(/(<head[^>]*>)/i, `$1${VIEWPORT_META}`);
    } else if (/<html[^>]*>/i.test(out)) {
      out = out.replace(/(<html[^>]*>)/i, `$1<head>${VIEWPORT_META}</head>`);
    } else {
      out = VIEWPORT_META + out;
    }
  }

  if (!out.includes("-webkit-text-size-adjust")) {
    out = /<\/head>/i.test(out)
      ? out.replace(/<\/head>/i, `${MOBILE_STYLE}</head>`)
      : MOBILE_STYLE + out;
  }

  return out;
}

// --------------------------------------------------------------- flood guard

// Per-app daily ceilings. ONLY apps with a measured baseline appear here; an
// app that is absent gets duplicate-detection but no numeric cap. Do not add an
// entry without measuring that app's real sends-per-recipient-per-day first.
// No type annotations anywhere below, on purpose — same constraint as the note
// inside mobileSafe. tests/test_resend_send_mobile_safe.py strips from
// `Deno.serve` to EOF and runs everything above it through plain node, which
// cannot parse TS syntax. These helpers sit above Deno.serve, so they must be
// valid plain JS. (They reference Deno.env / crypto.subtle, but only inside
// their bodies, which node never executes.)
const DAILY_CAPS = {
  astromedha: 18, // measured 2026-08-04: 5,610 recipient-days, max 9, ceiling 2x
};

export function appFor(from) {
  const m = /<([^>]+)>/.exec(from || "");
  const addr = (m ? m[1] : from || "").trim().toLowerCase();
  if (addr.endsWith("@astromedha.in") || addr.startsWith("astromedha@")) {
    return "astromedha";
  }
  if (addr.endsWith("@karibykriti.com")) return "kbk";
  const at = addr.indexOf("@");
  return at > 0 ? addr.slice(at + 1) : "unknown";
}

async function fingerprint(subject, html) {
  const data = new TextEncoder().encode(`${subject || ""} ${html || ""}`);
  const digest = await crypto.subtle.digest("SHA-256", data);
  return Array.from(new Uint8Array(digest))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("")
    .slice(0, 40);
}

function recipientsOf(to) {
  if (Array.isArray(to)) return to.map(String);
  if (typeof to === "string") return [to];
  return [];
}

/** true = send it. Fails OPEN: any error here returns true. */
async function allowSend(msg) {
  const url = Deno.env.get("SUPABASE_URL");
  const key = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");
  if (!url || !key) return { allow: true }; // no creds => fail open

  const to = recipientsOf(msg.to)[0];
  if (!to) return { allow: true };

  const app = appFor(String(msg.from ?? ""));
  const cap = DAILY_CAPS[app] ?? null;

  try {
    const fp = await fingerprint(String(msg.subject ?? ""), String(msg.html ?? ""));
    const res = await fetch(`${url}/rest/v1/rpc/empire_claim_send`, {
      method: "POST",
      headers: {
        apikey: key,
        authorization: `Bearer ${key}`,
        "content-type": "application/json",
      },
      body: JSON.stringify({
        p_recipient: to, p_fingerprint: fp, p_app: app, p_cap: cap,
        // The subject is what lets the guard tell a campaign apart from the
        // product someone PAID for. Without it empire_claim_send classifies
        // nothing, and the rolling weekly ceiling added 2026-08-22 can never
        // apply — which is deliberately how that migration shipped inert.
        //
        // It is only ever read against empire_send_policy.product_patterns to
        // decide exempt-vs-counted; nothing about the subject is stored beyond
        // that one-word verdict. The daily guidance, purchased reports,
        // transactional mail and our own [bracketed] ops alarms are exempt, so
        // a spam control can never throttle an outage alert or something a
        // customer bought.
        p_subject: String(msg.subject ?? ""),
        // Body and sender, for the operator-mail deferral lane only. The guard
        // stores these ONLY when empire_route_operator_mail says 'digest', and
        // that returns 'now' for every recipient not in
        // empire_operator_recipients - so a customer's body is never stored.
        // Migration 146's privacy note ("stores its verdict and not the subject
        // it judged") still holds for empire_send_guard itself, untouched.
        p_html: typeof msg.html === "string" ? msg.html : null,
        p_from: String(msg.from ?? ""),
      }),
      signal: AbortSignal.timeout(4000),
    });
    if (!res.ok) {
      console.error("send guard unreachable", res.status, "- failing OPEN");
      return { allow: true };
    }
    const verdict = await res.json();
    if (verdict && verdict.allow === false) {
      const reason = String(verdict.reason ?? "refused");
      // DEFERRED IS NOT A REFUSAL. The message was captured into
      // empire_operator_digest and goes out in the 07:00 IST digest, so the
      // caller must see success. Returning a 429 here would make ~108 cron jobs
      // log a failure for mail that was never lost - and Fleet Health would then
      // alarm on those failures, which is precisely the noise this lane exists
      // to remove. It would also be the second time a verdict got read as a rate
      // limit; see reference_chokepoint_429_is_a_verdict_not_a_rate_limit.
      if (reason === "deferred") {
        console.log("send DEFERRED to digest", JSON.stringify({ to, app }));
        return { allow: false, deferred: true, reason, to };
      }
      console.warn("send BLOCKED", JSON.stringify({ to, app, verdict }));
      return { allow: false, reason, to };
    }
    return { allow: true };
  } catch (err) {
    console.error("send guard errored - failing OPEN:", err);
    return { allow: true };
  }
}

Deno.serve(async (req: Request) => {
  const url = new URL(req.url);
  // Supabase may hand us "/resend-send/emails" or "/functions/v1/resend-send/emails"
  // depending on how it routes. Strip everything up to and including the function
  // name so BOTH shapes map to Resend's real path; default to /emails.
  const path = (url.pathname.replace(/^.*?resend-send/, "") || "/emails") + url.search;
  const auth = req.headers.get("authorization") ?? "";

  // TRANSPARENT PASSTHROUGH for everything that is not a send.
  //
  // Repos don't only POST /emails — they also GET /emails/{id} to read back what
  // was delivered, and hit /domains, /audiences etc. If this function only spoke
  // POST, then swapping a repo's base URL over would silently break those reads.
  // Being a full passthrough means "point the base URL here" is ALWAYS safe, which
  // is what lets the migration be mechanical instead of a per-call-site judgement.
  const isSend = req.method === "POST" && /^\/emails(\/batch)?(\?|$)/.test(path);

  if (!isSend) {
    const res = await fetch(`${RESEND_API}${path}`, {
      method: req.method,
      headers: { authorization: auth, "content-type": "application/json" },
      body: req.method === "GET" || req.method === "HEAD" ? undefined : await req.text(),
    });
    const text = await res.text();
    return new Response(text, {
      status: res.status,
      headers: { "content-type": "application/json" },
    });
  }

  const raw = await req.text();

  let body = raw;
  let patched = false;
  let parsed = null;
  try {
    const json = JSON.parse(raw);
    if (Array.isArray(json)) {
      // /emails/batch takes an array of messages.
      for (const m of json) {
        if (m && typeof m.html === "string") m.html = mobileSafe(m.html);
      }
      patched = true;
    } else if (json && typeof json.html === "string") {
      json.html = mobileSafe(json.html);
      patched = true;
    }
    if (patched) body = JSON.stringify(json);
    parsed = json;
  } catch (err) {
    // FAIL OPEN. A transform bug must never cost us an email — forward the
    // original bytes and let Resend decide.
    console.error("mobileSafe failed, forwarding raw:", err);
    body = raw;
    patched = false;
    parsed = null;
  }

  // Flood guard. Only runs when the body parsed — an unparseable body is
  // forwarded untouched, exactly as before.
  if (parsed) {
    if (Array.isArray(parsed)) {
      const kept = [];
      const refused = [];
      let deferred = 0;
      for (const m of parsed) {
        const v = await allowSend(m ?? {});
        if (v.allow) kept.push(m);
        else if (v.deferred) deferred += 1;
        else refused.push(`${v.to}:${v.reason}`);
      }
      if (refused.length) {
        console.warn(`batch: refused ${refused.length}`, JSON.stringify(refused));
      }
      if (deferred) {
        console.log(`batch: deferred ${deferred} to digest`);
      }
      if (!kept.length && deferred && !refused.length) {
        // Every message was DEFERRED, none refused. That is a success: the mail
        // is queued for the digest, so this must not 429.
        return new Response(
          JSON.stringify({ data: [], deferred }),
          { status: 200, headers: { "content-type": "application/json" } },
        );
      }
      if (!kept.length) {
        return new Response(
          JSON.stringify({
            name: "send_guard_refused",
            message: `every message in this batch was refused by the empire send guard (${refused.join(", ")})`,
          }),
          { status: 429, headers: { "content-type": "application/json" } },
        );
      }
      body = JSON.stringify(kept);
    } else {
      const v = await allowSend(parsed);
      if (v.deferred) {
        // Shaped like a Resend send so no caller has to know this lane exists.
        // The id is prefixed rather than random-looking on purpose: anything
        // that later reads it back from Resend gets a 404 it can explain.
        return new Response(
          JSON.stringify({ id: `deferred-${crypto.randomUUID()}`, deferred: true }),
          { status: 200, headers: { "content-type": "application/json" } },
        );
      }
      if (!v.allow) {
        return new Response(
          JSON.stringify({
            name: "send_guard_refused",
            message: `refused by the empire send guard: ${v.reason}. This recipient has already received this exact email today, or has hit the per-day ceiling. See empire_send_guard.`,
          }),
          { status: 429, headers: { "content-type": "application/json" } },
        );
      }
    }
  }

  const res = await fetch(`${RESEND_API}${path}`, {
    method: "POST",
    headers: {
      authorization: auth,
      "content-type": "application/json",
      // So we can tell, from Resend's side, which sends went through the proxy.
      "x-empire-mobile-safe": patched ? "1" : "0",
    },
    body,
  });

  // Pass Resend's response through verbatim — callers must not have to care.
  const text = await res.text();
  return new Response(text, {
    status: res.status,
    headers: { "content-type": "application/json" },
  });
});
