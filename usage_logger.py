"""Centralized API Usage Logger — logs Anthropic API calls to Supabase api_usage_log table."""
import json, logging, os, sys
import httpx

logger = logging.getLogger(__name__)

ANTHROPIC_PRICING = {
    "claude-sonnet-4-6": {"input": 3.0 / 1_000_000, "output": 15.0 / 1_000_000},
    "claude-sonnet-4-20250514": {"input": 3.0 / 1_000_000, "output": 15.0 / 1_000_000},
    "claude-opus-4-6": {"input": 15.0 / 1_000_000, "output": 75.0 / 1_000_000},
    "claude-haiku-4-5-20251001": {"input": 0.25 / 1_000_000, "output": 1.25 / 1_000_000},
}
_DEFAULT_PRICING = {"input": 3.0 / 1_000_000, "output": 15.0 / 1_000_000}

# --- OpenAI prices, verified 2026-07-10 --------------------------------------
# TTS bills per character; gpt-image-1 bills per image by size+quality; chat
# models bill per token. These are the only OpenAI models the empire calls.
OPENAI_TTS_PRICE_PER_CHAR = {"tts-1": 15.0 / 1_000_000, "tts-1-hd": 30.0 / 1_000_000}
OPENAI_IMAGE_PRICE = {("gpt-image-1", "low"): 0.011,
                      ("gpt-image-1", "medium"): 0.042,
                      ("gpt-image-1", "high"): 0.167}   # 1024x1024
OPENAI_TOKEN_PRICING = {"gpt-4o-mini": {"input": 0.15 / 1_000_000, "output": 0.60 / 1_000_000}}


def openai_tts_cost(model, chars):
    """USD for a text-to-speech call. None if the model isn't priced here."""
    rate = OPENAI_TTS_PRICE_PER_CHAR.get(model)
    return None if rate is None else round(chars * rate, 6)


def openai_image_cost(model, quality, n=1):
    """USD for an image-generation call. None if unpriced."""
    unit = OPENAI_IMAGE_PRICE.get((model, quality))
    return None if unit is None else round(unit * n, 6)


def openai_token_cost(model, input_tokens, output_tokens):
    """USD for a chat/vision call. None if unpriced."""
    p = OPENAI_TOKEN_PRICING.get(model)
    if p is None:
        return None
    return round(input_tokens * p["input"] + output_tokens * p["output"], 6)



def _get_supabase():
    """Resolve Supabase URL+key from env each call (no negative cache).

    Cloud Run jobs set SUPABASE_SERVICE_KEY; Streamlit apps set SUPABASE_KEY.
    Accept either so this logger works in both environments.
    """
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_KEY", "") or os.environ.get("SUPABASE_SERVICE_KEY", "")
    if not url or not key:
        try:
            import streamlit as st
            url = url or st.secrets.get("SUPABASE_URL", "")
            key = key or st.secrets.get("SUPABASE_KEY", "")
            if not url or not key:
                for sec in ("supabase", "connections.supabase", "database"):
                    try:
                        s = st.secrets.get(sec, {})
                        if not s:
                            continue
                        url = url or str(s.get("SUPABASE_URL", "") or s.get("url", ""))
                        key = key or str(s.get("SUPABASE_KEY", "") or s.get("key", ""))
                        if url and key:
                            break
                    except Exception:
                        continue
        except Exception:
            pass
    if not url or not key:
        return None
    return (url.rstrip("/"), key)


def log_usage(app, action, model, input_tokens=0, output_tokens=0, user_id=None, metadata=None, cost_usd=None):
    """Log an API call to Supabase. Non-fatal; prints to stderr on failure so
    misconfigured jobs surface instead of silently dropping telemetry.
    """
    try:
        config = _get_supabase()
        if not config:
            print(
                f"[usage_logger] accounting DROP app={app} action={action} — "
                f"SUPABASE env vars missing (URL_set={bool(os.environ.get('SUPABASE_URL'))} "
                f"KEY_set={bool(os.environ.get('SUPABASE_KEY'))} "
                f"SVCKEY_set={bool(os.environ.get('SUPABASE_SERVICE_KEY'))})",
                file=sys.stderr,
            )
            return
        url, key = config
        if cost_usd is None:
            # _DEFAULT_PRICING is Claude Sonnet's rate. Falling through to it for a
            # non-Anthropic model would silently invent a cost, so refuse instead.
            if not str(model).startswith("claude"):
                print(f"[usage_logger] accounting DROP app={app} action={action} "
                      f"model={model} — non-Anthropic model logged without an explicit "
                      f"cost_usd; token pricing would be wrong.", file=sys.stderr)
                return
            pricing = ANTHROPIC_PRICING.get(model, _DEFAULT_PRICING)
            cost_usd = (input_tokens * pricing["input"]) + (output_tokens * pricing["output"])
        row = {
            "app": app, "action": action, "model": model,
            "input_tokens": input_tokens, "output_tokens": output_tokens,
            "cost_usd": round(cost_usd, 6), "user_id": user_id,
            "metadata": metadata if metadata else None,
        }
        resp = httpx.post(
            f"{url}/rest/v1/api_usage_log",
            headers={"apikey": key, "Authorization": f"Bearer {key}",
                     "Content-Type": "application/json", "Prefer": "return=minimal"},
            json=row, timeout=5.0,
        )
        if resp.status_code >= 300:
            print(
                f"[usage_logger] POST api_usage_log -> HTTP {resp.status_code}: {resp.text[:200]}",
                file=sys.stderr,
            )
    except Exception as e:
        print(f"[usage_logger] log_usage failed: {type(e).__name__}: {e}", file=sys.stderr)
        logger.debug("Usage log failed (non-fatal): %s", e)
