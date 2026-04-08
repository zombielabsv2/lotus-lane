"""Centralized API Usage Logger — logs Anthropic API calls to Supabase api_usage_log table."""
import json, logging, os
from datetime import datetime
import httpx

logger = logging.getLogger(__name__)

ANTHROPIC_PRICING = {
    "claude-sonnet-4-6": {"input": 3.0 / 1_000_000, "output": 15.0 / 1_000_000},
    "claude-sonnet-4-20250514": {"input": 3.0 / 1_000_000, "output": 15.0 / 1_000_000},
    "claude-opus-4-6": {"input": 15.0 / 1_000_000, "output": 75.0 / 1_000_000},
    "claude-haiku-4-5-20251001": {"input": 0.25 / 1_000_000, "output": 1.25 / 1_000_000},
}
_DEFAULT_PRICING = {"input": 3.0 / 1_000_000, "output": 15.0 / 1_000_000}
_supabase_url = None
_supabase_key = None
_available = None

def _get_supabase():
    global _supabase_url, _supabase_key, _available
    if _available is not None:
        return (_supabase_url, _supabase_key) if _available else None
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_KEY", "")
    if not url:
        try:
            import streamlit as st
            url = st.secrets.get("SUPABASE_URL", "")
            key = key or st.secrets.get("SUPABASE_KEY", "")
        except Exception:
            pass
    if not url or not key:
        _available = False
        return None
    _supabase_url = url.rstrip("/")
    _supabase_key = key
    _available = True
    return (_supabase_url, _supabase_key)

def log_usage(app, action, model, input_tokens=0, output_tokens=0, user_id=None, metadata=None):
    """Log an API call to Supabase. Fails silently."""
    try:
        config = _get_supabase()
        if not config:
            return
        url, key = config
        pricing = ANTHROPIC_PRICING.get(model, _DEFAULT_PRICING)
        cost_usd = (input_tokens * pricing["input"]) + (output_tokens * pricing["output"])
        row = {
            "app": app, "action": action, "model": model,
            "input_tokens": input_tokens, "output_tokens": output_tokens,
            "cost_usd": round(cost_usd, 6), "user_id": user_id,
            "metadata": json.dumps(metadata) if metadata else None,
        }
        httpx.post(
            f"{url}/rest/v1/api_usage_log",
            headers={"apikey": key, "Authorization": f"Bearer {key}",
                     "Content-Type": "application/json", "Prefer": "return=minimal"},
            json=row, timeout=5.0,
        )
    except Exception as e:
        logger.debug("Usage log failed (non-fatal): %s", e)
