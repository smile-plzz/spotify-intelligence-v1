#!/usr/bin/env python3
"""
Hermes Token Usage Dashboard — single-file, zero-dependency.
Serves an interactive HTML dashboard with live data from ~/.hermes/state.db.

Usage:
    python3 token_dashboard.py              # starts on port 8765
    python3 token_dashboard.py --port 9000 # custom port
    python3 token_dashboard.py --browser   # auto-open browser

Stop with Ctrl+C. Data refreshes on every page load and via the /api/refresh
WebSocket-like SSE endpoint (auto-refresh every 30s in the UI).
"""

import json
import os
import sqlite3
import sys
import time
import datetime
import mimetypes
import threading
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

# ── Paths ──────────────────────────────────────────────────────────
HERMES_HOME = os.environ.get("HERMES_HOME", os.path.expanduser("~/.hermes"))
DB_PATH = os.path.join(HERMES_HOME, "state.db")
CONTEXT_CACHE = os.path.join(HERMES_HOME, "context_length_cache.yaml")
LOG_DIR = os.path.join(HERMES_HOME, "logs")
SESSION_DIR = os.path.join(HERMES_HOME, "sessions")

# ── Context limits (from cache + known defaults) ──────────────────
CONTEXT_LIMITS = {
    "upstage/solar-pro4:free": 524288,
    "google/gemini-3.6-flash": 1048576,
    "stepfun/step-3.7-flash:free": 524288,
    "upstage/solar-pro4:free@https://inference-api.nousresearch.com/v1": 524288,
    "google/gemini-3.6-flash@https://inference-api.nousresearch.com/v1": 1048576,
}
# Fallback known limits for models not in cache
KNOWN_LIMITS = {
    "upstage/solar-pro4:free": 524288,
    "google/gemini-3.6-flash": 1048576,
    "stepfun/step-3.7-flash:free": 524288,
    "google/gemini-3.6-flash": 1048576,
    "google/gemini-3.5-flash": 1048576,
    "google/gemini-3.1-flash-lite": 1048576,
    "google/gemini-3-flash-preview": 1048576,
    "google/gemini-2.5-flash": 1048576,
    "google/gemini-2.5-pro": 1048576,
    "openrouter/nvidia/nemotron-3-ultra-550b-a55b:free": 131072,
    "openrouter/groq/llama-3.3-70b-versatile": 128000,
    "openrouter/groq/llama-3.1-8b-instant": 128000,
    "openrouter/google/gemma-4-26b-a4b-it": 131072,
    "upstage/solar-pro4": 524288,
    "stepfun/step-3.7-flash": 524288,
    "stepfun/step-3.5-flash": 524288,
}


def get_context_limit(model: str) -> int:
    """Return context window size for a model, 0 if unknown."""
    if model in CONTEXT_LIMITS:
        return CONTEXT_LIMITS[model]
    if model in KNOWN_LIMITS:
        return KNOWN_LIMITS[model]
    # Try stripping gateway suffix
    clean = model.split("@")[0]
    if clean in KNOWN_LIMITS:
        return KNOWN_LIMITS[clean]
    if clean in CONTEXT_LIMITS:
        return CONTEXT_LIMITS[clean]
    return 0


def load_context_cache():
    """Parse context_length_cache.yaml for limits."""
    try:
        with open(CONTEXT_CACHE) as f:
            for line in f:
                line = line.strip()
                if ":" in line and not line.startswith("#") and not line.startswith("context"):
                    parts = line.split(":")
                    if len(parts) == 2:
                        key = parts[0].strip()
                        val = parts[1].strip()
                        try:
                            CONTEXT_LIMITS[key] = int(val)
                        except ValueError:
                            pass
    except FileNotFoundError:
        pass


load_context_cache()


# ── Data helpers ───────────────────────────────────────────────────

def row_to_dict(cursor, row):
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d


def db_query(query, params=()):
    conn = sqlite3.connect(DB_PATH, timeout=5)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(query, params)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def db_query_one(query, params=()):
    rows = db_query(query, params)
    return rows[0] if rows else None


# ── API endpoints ──────────────────────────────────────────────────

def api_session_model_usage():
    """Full session_model_usage with model config, limits, utilization %."""
    rows = db_query("""
        SELECT 
            su.session_id,
            su.model,
            su.billing_provider,
            su.billing_mode,
            su.api_call_count,
            su.input_tokens,
            su.output_tokens,
            su.cache_read_tokens,
            su.cache_write_tokens,
            su.reasoning_tokens,
            su.estimated_cost_usd,
            su.actual_cost_usd,
            su.cost_status,
            su.first_seen,
            su.last_seen,
            s.display_name,
            s.session_key,
            s.model_config,
            s.started_at,
            s.ended_at,
            s.message_count,
            s.tool_call_count
        FROM session_model_usage su
        LEFT JOIN sessions s ON su.session_id = s.id
        ORDER BY su.first_seen ASC
    """)
    
    for r in rows:
        r["context_limit"] = get_context_limit(r["model"])
        r["utilization_pct"] = (
            round((r["input_tokens"] / r["context_limit"]) * 100, 2)
            if r["context_limit"] > 0 else 0
        )
        # Cumulative total tokens for this session+model
        r["total_tokens"] = r["input_tokens"] + r["output_tokens"]
        # Session duration
        start = r.get("started_at") or 0
        end = r.get("ended_at") or time.time()
        r["duration_seconds"] = max(0, end - start)
        r["duration_human"] = format_duration(r["duration_seconds"])
        # Timestamp human
        r["first_seen_human"] = fmt_ts(r["first_seen"])
        r["last_seen_human"] = fmt_ts(r["last_seen"])
        # Display name from session_key if no display_name
        if not r.get("display_name") and r.get("session_key"):
            r["display_name"] = infer_display(r["session_key"])
        elif not r.get("display_name"):
            r["display_name"] = "CLI"
        # Platform
        r["platform"] = infer_platform(r.get("session_key", ""))
        # Model config pretty
        r["model_config_preview"] = preview_config(r.get("model_config"))
    
    return rows


def api_sessions_summary():
    """One row per session with totals."""
    rows = db_query("""
        SELECT 
            s.id,
            s.session_key,
            s.display_name,
            s.model,
            s.model_config,
            s.started_at,
            s.ended_at,
            s.message_count,
            s.tool_call_count,
            s.input_tokens,
            s.output_tokens,
            s.cache_read_tokens,
            s.cache_write_tokens,
            s.reasoning_tokens,
            s.billing_provider,
            s.billing_mode,
            s.estimated_cost_usd,
            s.actual_cost_usd,
            s.cost_status,
            s.pricing_version,
            s.title,
            s.last_activity_description
        FROM sessions s
        ORDER BY s.started_at ASC
    """)
    
    for r in rows:
        r["context_limit"] = get_context_limit(r["model"])
        r["utilization_pct"] = (
            round((r["input_tokens"] / r["context_limit"]) * 100, 2)
            if r["context_limit"] > 0 else 0
        )
        r["total_tokens"] = r["input_tokens"] + r["output_tokens"]
        start = r.get("started_at") or 0
        end = r.get("ended_at") or time.time()
        r["duration_seconds"] = max(0, end - start)
        r["duration_human"] = format_duration(r["duration_seconds"])
        r["started_at_human"] = fmt_ts(r["started_at"])
        r["ended_at_human"] = fmt_ts(r["ended_at"])
        if not r.get("display_name") and r.get("session_key"):
            r["display_name"] = infer_display(r["session_key"])
        r["platform"] = infer_platform(r.get("session_key", ""))
        r["model_config_preview"] = preview_config(r.get("model_config"))
    
    return rows


def api_model_aggregation():
    """Rollup by model."""
    rows = db_query("""
        SELECT 
            model,
            billing_provider,
            COUNT(DISTINCT session_id) as sessions,
            SUM(api_call_count) as total_calls,
            SUM(input_tokens) as total_input,
            SUM(output_tokens) as total_output,
            SUM(cache_read_tokens) as total_cache_read,
            SUM(cache_write_tokens) as total_cache_write,
            SUM(reasoning_tokens) as total_reasoning,
            SUM(estimated_cost_usd) as total_cost_usd,
            SUM(actual_cost_usd) as total_actual_cost
        FROM session_model_usage
        GROUP BY model, billing_provider
        ORDER BY total_input DESC
    """)
    
    for r in rows:
        r["context_limit"] = get_context_limit(r["model"])
        r["total_tokens"] = r["total_input"] + r["total_output"]
        r["cache_pct"] = (
            round((r["total_cache_read"] / r["total_input"]) * 100, 2)
            if r["total_input"] > 0 else 0
        )
        r["input_share_pct"] = 0  # filled in after
    
    total_input = sum(r["total_input"] for r in rows) or 1
    for r in rows:
        r["input_share_pct"] = round((r["total_input"] / total_input) * 100, 2)
    
    return rows


def api_channel_breakdown():
    """Group sessions by platform/user."""
    rows = db_query("""
        SELECT 
            s.session_key,
            s.display_name,
            s.model,
            s.input_tokens,
            s.output_tokens,
            s.cache_read_tokens,
            s.message_count,
            s.tool_call_count,
            s.started_at,
            s.ended_at,
            COUNT(DISTINCT su.session_id) as usage_rows
        FROM sessions s
        LEFT JOIN session_model_usage su ON s.id = su.session_id
        GROUP BY s.session_key, s.display_name, s.model
        ORDER BY s.input_tokens DESC
    """)
    
    for r in rows:
        r["platform"] = infer_platform(r["session_key"] or "")
        r["display_label"] = r["display_name"] or infer_display(r["session_key"] or "")
        if not r["display_label"] or r["display_label"] == "---":
            r["display_label"] = r["platform"]
        r["total_tokens"] = (r["input_tokens"] or 0) + (r["output_tokens"] or 0)
        r["duration_seconds"] = max(0, (r["ended_at"] or time.time()) - (r["started_at"] or 0))
        r["duration_human"] = format_duration(r["duration_seconds"])
    
    # Aggregate by platform+display_label
    from collections import defaultdict
    agg = defaultdict(lambda: {
        "platform": "", "display_label": "", "sessions": 0,
        "input_tokens": 0, "output_tokens": 0, "cache_read": 0,
        "messages": 0, "api_calls": 0, "total_tokens": 0,
        "duration_seconds": 0
    })
    for r in rows:
        key = (r["platform"], r["display_label"])
        a = agg[key]
        a["platform"] = r["platform"]
        a["display_label"] = r["display_label"] or r["platform"]
        a["sessions"] += 1
        a["input_tokens"] += r["input_tokens"] or 0
        a["output_tokens"] += r["output_tokens"] or 0
        a["cache_read"] += r["cache_read_tokens"] or 0
        a["messages"] += r["message_count"] or 0
        a["api_calls"] += r["usage_rows"]
        a["total_tokens"] += r["total_tokens"]
        a["duration_seconds"] += r["duration_seconds"]
    
    result = list(agg.values())
    total_in = sum(a["input_tokens"] for a in result) or 1
    for a in result:
        a["input_share_pct"] = round((a["input_tokens"] / total_in) * 100, 2)
        a["duration_human"] = format_duration(a["duration_seconds"])
    result.sort(key=lambda x: -x["input_tokens"])
    return result


def api_dashboard_summary():
    """Compact summary for the top card of the dashboard."""
    smu = db_query("""
        SELECT 
            COUNT(*) as request_files,
            SUM(input_tokens) as total_input,
            SUM(output_tokens) as total_output,
            SUM(cache_read_tokens) as total_cache_read,
            SUM(cache_write_tokens) as total_cache_write,
            SUM(reasoning_tokens) as total_reasoning,
            SUM(api_call_count) as total_calls,
            COUNT(DISTINCT session_id) as unique_sessions,
            SUM(estimated_cost_usd) as total_cost
        FROM session_model_usage
    """)
    smu = smu[0] if smu else {}
    
    sessions = db_query_one("""
        SELECT COUNT(*) as session_count,
               SUM(input_tokens) as sess_input,
               SUM(output_tokens) as sess_output,
               SUM(cache_read_tokens) as sess_cache_read
        FROM sessions
    """)
    
    # Model-level
    models = db_query("""
        SELECT model, SUM(input_tokens) as total_input,
               SUM(output_tokens) as total_output,
               COUNT(DISTINCT session_id) as sessions
        FROM session_model_usage
        GROUP BY model
        ORDER BY total_input DESC
    """)
    
    # Largest single session
    largest = db_query_one("""
        SELECT session_id, input_tokens, output_tokens, model,
               (input_tokens + output_tokens) as total_tokens
        FROM session_model_usage
        ORDER BY input_tokens DESC
        LIMIT 1
    """)
    
    return {
        "total_input": smu.get("total_input") or 0,
        "total_output": smu.get("total_output") or 0,
        "total_cache_read": smu.get("total_cache_read") or 0,
        "total_cache_write": smu.get("total_cache_write") or 0,
        "total_reasoning": smu.get("total_reasoning") or 0,
        "total_calls": smu.get("total_calls") or 0,
        "unique_sessions_smu": smu.get("unique_sessions") or 0,
        "session_count": sessions.get("session_count") or 0,
        "models": [
            {
                "model": m["model"],
                "input": m["total_input"],
                "output": m["total_output"],
                "sessions": m["sessions"],
                "context_limit": get_context_limit(m["model"]),
                "utilization_pct": round((m["total_input"] / get_context_limit(m["model"]) * 100), 2) if get_context_limit(m["model"]) > 0 else 0,
            } for m in models
        ],
        "largest_session": largest,
        "grand_total_tokens": (smu.get("total_input") or 0) + (smu.get("total_output") or 0),
        "cache_hit_pct": round(
            ((smu.get("total_cache_read") or 0) / (smu.get("total_input") or 1)) * 100, 2
        ),
        "updated_at": time.time(),
    }


def api_token_timeline():
    """Token usage over time — bucket by hour for the chart."""
    rows = db_query("""
        SELECT 
            session_id,
            model,
            first_seen,
            last_seen,
            input_tokens,
            output_tokens,
            cache_read_tokens,
            reasoning_tokens
        FROM session_model_usage
        ORDER BY first_seen ASC
    """)
    
    # Build hourly buckets
    buckets = {}
    for r in rows:
        ts = r["first_seen"]
        hour_key = int(ts / 3600) * 3600  # floor to hour
        if hour_key not in buckets:
            buckets[hour_key] = {
                "hour": hour_key,
                "input": 0, "output": 0, "cache_read": 0,
                "reasoning": 0, "sessions": set(), "models": set()
            }
        b = buckets[hour_key]
        b["input"] += r["input_tokens"]
        b["output"] += r["output_tokens"]
        b["cache_read"] += r["cache_read_tokens"]
        b["reasoning"] += r["reasoning_tokens"]
        b["sessions"].add(r["session_id"])
        b["models"].add(r["model"])
    
    result = []
    for hk in sorted(buckets):
        b = buckets[hk]
        result.append({
            "hour": b["hour"],
            "hour_human": datetime.datetime.fromtimestamp(b["hour"]).strftime("%Y-%m-%d %H:%M"),
            "input": b["input"],
            "output": b["output"],
            "cache_read": b["cache_read"],
            "reasoning": b["reasoning"],
            "session_count": len(b["sessions"]),
            "model_count": len(b["models"]),
        })
    return result


def api_active_sessions():
    """Sessions that look active (no end time, recent activity)."""
    rows = db_query("""
        SELECT id, session_key, display_name, model, started_at,
               input_tokens, output_tokens, cache_read_tokens,
               message_count, tool_call_count, last_activity_at,
               last_activity_description
        FROM sessions
        WHERE ended_at = 0 OR ended_at IS NULL
        ORDER BY started_at DESC
    """)
    for r in rows:
        sk = r.get("session_key") or r.get("id") or "unknown"
        r["session_key"] = sk
        dn = r.get("display_name")
        if not dn or dn == "---":
            r["display_name"] = infer_display(sk)
        r["platform"] = infer_platform(sk)
        r["display_label"] = r["display_name"] or infer_display(sk) or "Unknown"
        r["age_seconds"] = time.time() - (r.get("started_at") or 0)
        r["age_human"] = format_duration(r["age_seconds"])
    return rows


def api_alerts():
    """Compute alerts: sessions approaching context limits, big spenders, etc."""
    alerts = []
    
    # Sessions with high cumulative token count (per-session model usage)
    smu = db_query("""
        SELECT session_id, model, input_tokens, output_tokens,
               api_call_count, first_seen, last_seen
        FROM session_model_usage
        ORDER BY input_tokens DESC
        LIMIT 20
    """)
    for r in smu:
        limit = get_context_limit(r["model"])
        pct = (r["input_tokens"] / limit * 100) if limit > 0 else 0
        if pct > 100:
            alerts.append({
                "level": "warning",
                "type": "high_cumulative_tokens",
                "msg": f"Session {r['session_id'][-20:]} with {r['model']} has {r['input_tokens']:,} cumulative input tokens — {pct:.0f}% of {limit:,} context limit (across {r['api_call_count']} API calls). Individual calls are within limit but session is token-heavy.",
                "session_id": r["session_id"],
                "model": r["model"],
                "input_tokens": r["input_tokens"],
                "utilization_pct": round(pct, 1),
                "context_limit": limit,
            })
    
    # Sessions with zero end time (potentially orphaned)
    orphaned = db_query("""
        SELECT id, session_key, display_name, model, started_at, input_tokens
        FROM sessions
        WHERE (ended_at = 0 OR ended_at IS NULL)
          AND started_at < (strftime('%s','now') - 3600)
        ORDER BY started_at ASC
    """)
    now = time.time()
    for r in orphaned:
        age = (now - (r["started_at"] or 0) if r["started_at"] else 0)
        sk = r.get("session_key") or ""
        if sk:
            label = r.get("display_name") or sk[-30:]
        else:
            label = r.get("display_name") or (r.get("id") or "unknown")[-30:]
        alerts.append({
            "level": "info",
            "type": "orphaned_session",
            "msg": f"Session '{label}' started {format_duration(age)} ago with no end time. Input tokens: {r['input_tokens']:,}.",
            "session_id": r["id"],
            "age_seconds": age,
        })
    
    # Request dump errors — quick count from DB only (no file scanning)
    dump_errors = db_query("""
        SELECT COUNT(*) as cnt FROM sessions WHERE input_tokens > 0 AND message_count = 0
    """)
    # Skip file scanning — too slow for real-time
    
    return alerts


# ── Helper functions ───────────────────────────────────────────────

def format_duration(seconds):
    if seconds < 60:
        return f"{seconds:.0f}s"
    if seconds < 3600:
        return f"{seconds/60:.1f}m"
    if seconds < 86400:
        return f"{seconds/3600:.1f}h"
    return f"{seconds/86400:.1f}d"


def fmt_ts(ts):
    if not ts:
        return "—"
    try:
        return datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
    except:
        return "—"


def infer_platform(session_key):
    if not session_key:
        return "CLI"
    sk = session_key.lower()
    if "telegram" in sk:
        return "Telegram"
    if "discord" in sk:
        return "Discord"
    if "whatsapp" in sk:
        return "WhatsApp"
    if "email" in sk:
        return "Email"
    if "slack" in sk:
        return "Slack"
    if "teams" in sk:
        return "Teams"
    if "agent:main" in sk:
        return "Gateway"
    return "CLI"


def infer_display(session_key):
    if not session_key:
        return "Unknown"
    # Extract user/channel info from session key
    parts = session_key.split(":")
    
    if session_key.startswith("agent:main:telegram:dm:"):
        uid = parts[-1] if len(parts) > 4 else ""
        names = {"2134986302": "Haddock", "6342323077": "Safia Ishrak"}
        return names.get(uid, f"Telegram User {uid}")
    
    if session_key.startswith("agent:main:telegram:group:"):
        gid = parts[-1] if len(parts) > 4 else ""
        if "blurt" in session_key.lower():
            return "Blurt x Alfred"
        return f"Telegram Group {gid}"
    
    if session_key.startswith(":main:discord:dm:"):
        uid = parts[-1] if len(parts) > 2 else ""
        names = {"1537006300825780295": "captainlewra"}
        return names.get(uid, f"Discord User {uid}")
    
    if "batcave" in session_key.lower() or "captain" in session_key.lower():
        # Extract channel or user
        if len(parts) >= 2 and parts[0].isdigit():
            return "CaptainL's Batcave"
        return "CaptainL's Batcave"
    
    if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
        return f"Channel {parts[0][:15]}"
    
    return session_key[:40]


def preview_config(cfg_str):
    if not cfg_str:
        return "—"
    try:
        cfg = json.loads(cfg_str)
        parts = []
        if cfg.get("max_iterations"):
            parts.append(f"max_iter={cfg['max_iterations']}")
        if cfg.get("reasoning_config", {}).get("enabled"):
            parts.append(f"reasoning={cfg['reasoning_config'].get('effort', 'on')}")
        if cfg.get("gateway_runtime"):
            parts.append(f"via={cfg['gateway_runtime'].get('provider', '?')}")
        if cfg.get("_delegate_from"):
            parts.append(f"handoff_from={cfg['_delegate_from'][-15:]}")
        return ", ".join(parts) if parts else "default config"
    except:
        return str(cfg_str)[:60]


# ── HTTP Server ────────────────────────────────────────────────────

DASHBOARD_PORT = int(os.environ.get("DASHBOARD_PORT", 8765))

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Hermes Token Dashboard — Ismail Hossain</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.min.js"></script>
<style>
  :root {
    --bg: #0d1117;
    --surface: #161b22;
    --border: #30363d;
    --text: #e6edf3;
    --muted: #8b949e;
    --accent: #f0883e;
    --green: #3fb950;
    --red: #f85149;
    --blue: #58a6ff;
    --yellow: #d29922;
    --purple: #a371f7;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: var(--bg);
    color: var(--text);
    min-height: 100vh;
    padding: 20px;
  }
  .container { max-width: 1400px; margin: 0 auto; }
  
  /* Header */
  .header {
    display: flex; justify-content: space-between; align-items: center;
    margin-bottom: 24px; padding-bottom: 16px;
    border-bottom: 1px solid var(--border);
  }
  .header h1 { font-size: 24px; font-weight: 600; }
  .header .subtitle { color: var(--muted); font-size: 13px; margin-top: 4px; }
  .header .refresh-btn {
    background: var(--surface); border: 1px solid var(--border);
    color: var(--text); padding: 8px 16px; border-radius: 6px;
    cursor: pointer; font-size: 13px; font-family: inherit;
    transition: all 0.15s;
  }
  .header .refresh-btn:hover { border-color: var(--accent); color: var(--accent); }
  .header .last-updated { color: var(--muted); font-size: 12px; margin-top: 4px; }
  
  /* KPI Cards */
  .kpi-grid {
    display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 12px; margin-bottom: 24px;
  }
  .kpi-card {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 8px; padding: 16px;
  }
  .kpi-card .label { font-size: 11px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.05em; }
  .kpi-card .value { font-size: 28px; font-weight: 700; margin-top: 4px; }
  .kpi-card .sub { font-size: 12px; color: var(--muted); margin-top: 2px; }
  .kpi-card.accent .value { color: var(--accent); }
  .kpi-card.green .value { color: var(--green); }
  .kpi-card.blue .value { color: var(--blue); }
  .kpi-card.purple .value { color: var(--purple); }
  .kpi-card.red .value { color: var(--red); }
  
  /* Grid layout */
  .grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 24px; }
  .grid-3 { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 16px; margin-bottom: 24px; }
  .panel {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 8px; padding: 16px;
  }
  .panel h2 {
    font-size: 14px; font-weight: 600; margin-bottom: 12px;
    display: flex; align-items: center; gap: 8px;
  }
  .panel h2 .badge {
    font-size: 10px; font-weight: 500; padding: 2px 8px;
    border-radius: 10px; background: var(--border); color: var(--muted);
  }
  
  /* Alerts */
  .alert {
    padding: 10px 14px; border-radius: 6px; margin-bottom: 8px;
    font-size: 13px; line-height: 1.5;
  }
  .alert.error { background: rgba(248,81,73,0.15); border-left: 3px solid var(--red); color: #ffb3b0; }
  .alert.warning { background: rgba(210,153,34,0.15); border-left: 3px solid var(--yellow); color: #f0d080; }
  .alert.info { background: rgba(88,166,255,0.1); border-left: 3px solid var(--blue); color: #b0c8ff; }
  .alert .alert-title { font-weight: 600; margin-bottom: 2px; }
  
  /* Tables */
  .table-wrap { overflow-x: auto; }
  table { width: 100%; border-collapse: collapse; font-size: 12px; }
  th { text-align: left; padding: 8px 12px; color: var(--muted); font-weight: 500; border-bottom: 1px solid var(--border); white-space: nowrap; cursor: pointer; user-select: none; }
  th:hover { color: var(--text); }
  th .sort-arrow { opacity: 0.3; margin-left: 4px; }
  th.sorted .sort-arrow { opacity: 1; color: var(--accent); }
  td { padding: 8px 12px; border-bottom: 1px solid #21262d; white-space: nowrap; }
  tr:hover td { background: #1c2128; }
  .num { text-align: right; font-variant-numeric: tabular-nums; }
  .status-ok { color: var(--green); }
  .status-warn { color: var(--yellow); }
  .status-danger { color: var(--red); }
  
  /* Context bar */
  .context-bar-wrap { margin-top: 6px; }
  .context-bar-label { font-size: 11px; color: var(--muted); display: flex; justify-content: space-between; }
  .context-bar-track { height: 6px; background: #21262d; border-radius: 3px; margin-top: 2px; overflow: hidden; }
  .context-bar-fill { height: 100%; border-radius: 3px; transition: width 0.3s; }
  .context-bar-fill.safe { background: var(--green); }
  .context-bar-fill.warn { background: var(--yellow); }
  .context-bar-fill.danger { background: var(--red); }
  
  /* Chart containers */
  .chart-container { position: relative; height: 250px; }
  .chart-container.tall { height: 350px; }
  
  /* Filters */
  .filters { display: flex; gap: 8px; margin-bottom: 12px; flex-wrap: wrap; align-items: center; }
  .filters select, .filters input {
    background: #0d1117; border: 1px solid var(--border); color: var(--text);
    padding: 6px 10px; border-radius: 6px; font-size: 12px; font-family: inherit;
  }
  .filters input[type="text"] { width: 200px; }
  .filters label { font-size: 12px; color: var(--muted); }
  
  /* Modal */
  .modal-overlay {
    display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.7);
    z-index: 100; align-items: center; justify-content: center;
  }
  .modal-overlay.active { display: flex; }
  .modal {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 12px; padding: 24px; max-width: 600px; width: 90%;
    max-height: 80vh; overflow-y: auto;
  }
  .modal h2 { font-size: 18px; margin-bottom: 16px; }
  .modal-close {
    float: right; background: none; border: none; color: var(--muted);
    font-size: 20px; cursor: pointer; padding: 4px;
  }
  .modal-close:hover { color: var(--text); }
  
  /* Empty state */
  .empty { text-align: center; padding: 40px; color: var(--muted); }
  
  @media (max-width: 900px) {
    .grid-2, .grid-3 { grid-template-columns: 1fr; }
  }
</style>
</head>
<body>
<div class="container">
  <!-- Header -->
  <div class="header">
    <div>
      <h1>Hermes Token Usage Dashboard</h1>
      <div class="subtitle">Ismail Hossain · Solar Pro 4 via Nous · Live data from state.db</div>
    </div>
    <div>
      <button class="refresh-btn" onclick="refreshAll()">⟳ Refresh</button>
      <div class="last-updated" id="lastUpdated">—</div>
    </div>
  </div>

  <!-- KPI Cards -->
  <div class="kpi-grid" id="kpiGrid"></div>

  <!-- Alerts -->
  <div class="panel" id="alertsPanel" style="margin-bottom:24px; display:none;">
    <h2>⚠ Alerts &amp; Notices <span class="badge" id="alertCount">0</span></h2>
    <div id="alertsList"></div>
  </div>

  <!-- Charts Row -->
  <div class="grid-3">
    <div class="panel">
      <h2>Token Distribution by Model</h2>
      <div class="chart-container"><canvas id="chartModelDist"></canvas></div>
    </div>
    <div class="panel">
      <h2>Input vs Output vs Cache <span class="badge">stacked</span></h2>
      <div class="chart-container"><canvas id="chartStacked"></canvas></div>
    </div>
    <div class="panel">
      <h2>Token Timeline (per hour)</h2>
      <div class="chart-container tall"><canvas id="chartTimeline"></canvas></div>
    </div>
  </div>

  <!-- Model Comparison + Channel Breakdown -->
  <div class="grid-2">
    <div class="panel">
      <h2>Model Comparison <span class="badge">context limits · utilization</span></h2>
      <div class="table-wrap">
        <table id="modelTable"><thead><tr>
          <th data-sort="model">Model</th>
          <th data-sort="context_limit" class="num">Context Limit</th>
          <th data-sort="total_input" class="num">Total Input</th>
          <th data-sort="total_output" class="num">Total Output</th>
          <th data-sort="total_cache_read" class="num">Cache Read</th>
          <th data-sort="input_share_pct" class="num">Share</th>
          <th data-sort="sessions" class="num">Sessions</th>
          <th>Utilization</th>
        </tr></thead><tbody></tbody></table>
      </div>
    </div>
    <div class="panel">
      <h2>Channel / Platform Breakdown</h2>
      <div class="table-wrap">
        <table id="channelTable"><thead><tr>
          <th data-sort="platform">Platform</th>
          <th data-sort="display_label">Channel / User</th>
          <th data-sort="sessions" class="num">Sessions</th>
          <th data-sort="input_tokens" class="num">Input</th>
          <th data-sort="output_tokens" class="num">Output</th>
          <th data-sort="input_share_pct" class="num">Share</th>
          <th data-sort="duration_human">Duration</th>
        </tr></thead><tbody></tbody></table>
      </div>
    </div>
  </div>

  <!-- Session Detail Table -->
  <div class="panel" style="margin-bottom:24px;">
    <div class="filters">
      <label>Filter:</label>
      <input type="text" id="sessionFilter" placeholder="Search session, model, platform..." oninput="filterSessions()">
      <label>Model:</label>
      <select id="modelFilter" onchange="filterSessions()">
        <option value="">All models</option>
      </select>
      <label>Platform:</label>
      <select id="platformFilter" onchange="filterSessions()">
        <option value="">All platforms</option>
        <option value="CLI">CLI</option>
        <option value="Telegram">Telegram</option>
        <option value="Discord">Discord</option>
        <option value="Gateway">Gateway</option>
      </select>
    </div>
    <div class="table-wrap">
      <table id="sessionTable"><thead><tr>
        <th data-sort="session_id">Session</th>
        <th data-sort="display_name">Display</th>
        <th data-sort="platform">Platform</th>
        <th data-sort="model">Model</th>
        <th data-sort="input_tokens" class="num">Input</th>
        <th data-sort="output_tokens" class="num">Output</th>
        <th data-sort="cache_read_tokens" class="num">Cache Read</th>
        <th data-sort="reasoning_tokens" class="num">Reasoning</th>
        <th data-sort="api_call_count" class="num">API Calls</th>
        <th data-sort="duration_human">Duration</th>
        <th data-sort="utilization_pct" class="num">Util %</th>
        <th data-sort="first_seen_human">Started</th>
        <th>Context Bar</th>
        <th></th>
      </tr></thead><tbody></tbody></table>
    </div>
  </div>

  <!-- Active Sessions -->
  <div class="panel" id="activePanel" style="margin-bottom:24px;">
    <h2>🔴 Active Sessions (no end time) <span class="badge" id="activeCount">0</span></h2>
    <div id="activeList"></div>
  </div>

  <!-- Footer note -->
  <div style="text-align:center; color:var(--muted); font-size:11px; padding:20px 0; border-top:1px solid var(--border);">
    Data sourced from <code>~/.hermes/state.db</code> (session_model_usage + sessions tables) ·
    Context limits from <code>context_length_cache.yaml</code> + known defaults ·
    <span id="footerNote"></span>
  </div>
</div>

// Session Detail Modal -->
<div class="modal-overlay" id="sessionModal">
  <div class="modal">
    <button class="modal-close" onclick="closeModal()">×</button>
    <h2 id="modalTitle">Session Details</h2>
    <div id="modalBody"></div>
  </div>
</div>

<script>
// ── Context limits from server ─────────────────────────────────────
const CONTEXT_LIMITS = {{ CONTEXT_LIMITS_JSON }};
const CONTEXT_COUNT = {{ CONTEXT_COUNT }};
// ── State ──────────────────────────────────────────────────────────
let allSessionData = [];
let currentSort = { key: 'first_seen_human', dir: 'asc' };
let modelChart = null;
let stackedChart = null;
let timelineChart = null;

// ── Format helpers ──────────────────────────────────────────────────
function fmtNum(n) {
  if (n == null || isNaN(n)) return '—';
  if (n >= 1e9) return (n / 1e9).toFixed(2) + 'B';
  if (n >= 1e6) return (n / 1e6).toFixed(2) + 'M';
  if (n >= 1e3) return (n / 1e3).toFixed(1) + 'K';
  return n.toLocaleString();
}
function fmtInt(n) {
  if (n == null || isNaN(n)) return '—';
  return n.toLocaleString();
}
function fmtDuration(s) {
  if (s == null || isNaN(s) || s < 0) return '—';
  if (s < 60) return s.toFixed(0) + 's';
  if (s < 3600) return (s/60).toFixed(1) + 'm';
  if (s < 86400) return (s/3600).toFixed(1) + 'h';
  return (s/86400).toFixed(1) + 'd';
}

// ── API call ───────────────────────────────────────────────────────
async function api(path) {
  const res = await fetch(path);
  if (!res.ok) throw new Error('API ' + path + ' returned ' + res.status);
  return res.json();
}

// ── Render KPI cards ───────────────────────────────────────────────
function renderKPIs(summary) {
  const grid = document.getElementById('kpiGrid');
  const cards = [
    { label: 'Total Input Tokens', value: fmtNum(summary.total_input), cls: 'accent', sub: summary.models.length + ' model(s) used' },
    { label: 'Total Output Tokens', value: fmtNum(summary.total_output), cls: 'green', sub: 'Across ' + summary.total_calls + ' API calls' },
    { label: 'Grand Total (In+Out)', value: fmtNum(summary.grand_total_tokens), cls: 'blue', sub: summary.unique_sessions_smu + ' session-model combos' },
    { label: 'Cache Read Tokens', value: fmtNum(summary.total_cache_read), cls: 'purple', sub: summary.cache_hit_pct + '% cache hit rate' },
    { label: 'Cache Write Tokens', value: fmtNum(summary.total_cache_write), cls: '', sub: '0 — provider-side caching' },
    { label: 'Reasoning Tokens', value: fmtNum(summary.total_reasoning), cls: 'yellow', sub: 'Thinking/output tokens' },
    { label: 'API Calls', value: fmtInt(summary.total_calls), cls: '', sub: summary.unique_sessions_smu + ' unique sessions' },
    { label: 'Total Sessions (all)', value: fmtInt(summary.session_count), cls: '', sub: 'From sessions table' },
  ];
  if (summary.largest_session) {
    cards.push({
      label: 'Largest Session',
      value: fmtNum(summary.largest_session.total_tokens),
      cls: 'red',
      sub: summary.largest_session.session_id.slice(-25) + ' · ' + summary.largest_session.model
    });
  }
  grid.innerHTML = cards.map(c => `
    <div class="kpi-card ${c.cls}">
      <div class="label">${c.label}</div>
      <div class="value">${c.value}</div>
      <div class="sub">${c.sub}</div>
    </div>
  `).join('');
}

// ── Render alerts ──────────────────────────────────────────────────
function renderAlerts(alerts) {
  const panel = document.getElementById('alertsPanel');
  const list = document.getElementById('alertsList');
  const count = document.getElementById('alertCount');
  if (!alerts || alerts.length === 0) {
    panel.style.display = 'none';
    return;
  }
  panel.style.display = 'block';
  count.textContent = alerts.length;
  list.innerHTML = alerts.map(a => `
    <div class="alert ${a.level}">
      <div class="alert-title">${a.type.replace(/_/g,' ')}</div>
      ${a.msg}
    </div>
  `).join('');
}

// ── Render model table ─────────────────────────────────────────────
function renderModelTable(models) {
  const tbody = document.querySelector('#modelTable tbody');
  tbody.innerHTML = models.map((m, i) => {
    const limit = m.context_limit || 0;
    const pct = m.utilization_pct || 0;
    let barClass = 'safe';
    if (pct > 100) barClass = 'danger';
    else if (pct > 50) barClass = 'warn';
    // utilization is cumulative — it's always >100 for big sessions, so show "per-call" note
    const barW = Math.min(100, pct);
    return `
      <tr>
        <td><code style="color:var(--blue)">${m.model}</code></td>
        <td class="num">${limit > 0 ? fmtInt(limit) : '<span style="color:var(--muted)">unknown</span>'}</td>
        <td class="num">${fmtInt(m.total_input)}</td>
        <td class="num">${fmtInt(m.total_output)}</td>
        <td class="num">${fmtInt(m.total_cache_read)}</td>
        <td class="num">${m.input_share_pct.toFixed(1)}%</td>
        <td class="num">${m.sessions}</td>
        <td>
          <div class="context-bar-wrap">
            <div class="context-bar-label">
              <span>${pct.toFixed(0)}% of ${limit > 0 ? fmtInt(limit) : '∞'}</span>
              <span>cumulative</span>
            </div>
            <div class="context-bar-track">
              <div class="context-bar-fill ${barClass}" style="width:${barW}%"></div>
            </div>
          </div>
        </td>
      </tr>`;
  }).join('');
  sortTable('modelTable');
}

// ── Render channel table ───────────────────────────────────────────
function renderChannelTable(channels) {
  const tbody = document.querySelector('#channelTable tbody');
  tbody.innerHTML = channels.map(c => `
    <tr>
      <td>${c.platform}</td>
      <td>${c.display_label}</td>
      <td class="num">${c.sessions}</td>
      <td class="num">${fmtInt(c.input_tokens)}</td>
      <td class="num">${fmtInt(c.output_tokens)}</td>
      <td class="num">${c.input_share_pct.toFixed(1)}%</td>
      <td>${c.duration_human}</td>
    </tr>
  `).join('');
  sortTable('channelTable');
}

// ── Render session table ───────────────────────────────────────────
function renderSessionTable(sessions) {
  allSessionData = sessions;
  const tbody = document.querySelector('#sessionTable tbody');
  const{modelFilter, platformFilter} = getFilters();
  
  let filtered = sessions.filter(s => {
    if (modelFilter && s.model !== modelFilter) return false;
    if (platformFilter && s.platform !== platformFilter) return false;
    return true;
  });
  
  if (document.getElementById('sessionFilter').value) {
    const q = document.getElementById('sessionFilter').value.toLowerCase();
    filtered = filtered.filter(s =>
      (s.session_id || '').toLowerCase().includes(q) ||
      (s.display_name || '').toLowerCase().includes(q) ||
      (s.platform || '').toLowerCase().includes(q) ||
      (s.model || '').toLowerCase().includes(q)
    );
  }
  
  tbody.innerHTML = filtered.map(s => {
    const limit = s.context_limit || 0;
    const pct = s.utilization_pct || 0;
    const barW = Math.min(100, pct);
    let barClass = 'safe';
    if (pct > 100) barClass = 'danger';
    else if (pct > 50) barClass = 'warn';
    
    const utilDisplay = limit > 0
      ? `${pct.toFixed(0)}% of ${fmtInt(limit)}`
      : '—';
    
    return `
      <tr onclick="openSessionModal('${s.session_id}')" style="cursor:pointer">
        <td><code style="color:var(--blue);font-size:11px">${s.session_id}</code></td>
        <td>${s.display_name || '—'}</td>
        <td>${s.platform}</td>
        <td><code style="color:var(--accent);font-size:11px">${s.model || '—'}</code></td>
        <td class="num">${fmtInt(s.input_tokens)}</td>
        <td class="num">${fmtInt(s.output_tokens)}</td>
        <td class="num">${fmtInt(s.cache_read_tokens)}</td>
        <td class="num">${fmtInt(s.reasoning_tokens)}</td>
        <td class="num">${fmtInt(s.api_call_count || 0)}</td>
        <td>${s.duration_human || '—'}</td>
        <td class="num ${pct > 100 ? 'status-danger' : pct > 50 ? 'status-warn' : ''}">${utilDisplay}</td>
        <td style="color:var(--muted);font-size:11px">${s.first_seen_human || '—'}</td>
        <td>
          <div class="context-bar-wrap">
            <div class="context-bar-track">
              <div class="context-bar-fill ${barClass}" style="width:${barW}%" title="${utilDisplay}"></div>
            </div>
          </div>
        </td>
        <td><span style="color:var(--muted);font-size:11px">${s.model_config_preview || '—'}</span></td>
      </tr>`;
  }).join('');
  
  // Populate model filter dropdown
  const models = [...new Set(sessions.map(s => s.model).filter(Boolean))].sort();
  const mf = document.getElementById('modelFilter');
  mf.innerHTML = '<option value="">All models</option>' + models.map(m =>
    `<option value="${m}" ${m === modelFilter ? 'selected' : ''}>${m}</option>`
  ).join('');
  
  sortTable('sessionTable');
}

function getFilters() {
  return {
    modelFilter: document.getElementById('modelFilter').value,
    platformFilter: document.getElementById('platformFilter').value,
  };
}

function filterSessions() {
  renderSessionTable(allSessionData);
}

// ── Sort tables ────────────────────────────────────────────────────
function sortTable(tableId) {
  const ths = document.querySelectorAll('#' + tableId + ' th[data-sort]');
  ths.forEach(th => {
    th.classList.toggle('sorted', th.dataset.sort === currentSort.key);
    const arrow = th.querySelector('.sort-arrow') || (() => {
      const a = document.createElement('span');
      a.className = 'sort-arrow';
      a.textContent = currentSort.dir === 'asc' ? '▲' : '▼';
      th.appendChild(a);
      return a;
    })();
    arrow.textContent = th.dataset.sort === currentSort.key
      ? (currentSort.dir === 'asc' ? '▲' : '▼') : '▲';
  });
}

function handleSort(e) {
  const th = e.currentTarget;
  const key = th.dataset.sort;
  if (currentSort.key === key) {
    currentSort.dir = currentSort.dir === 'asc' ? 'desc' : 'asc';
  } else {
    currentSort.key = key;
    currentSort.dir = 'asc';
  }
  // Re-render current table
  const tbody = th.closest('table').querySelector('tbody');
  const rows = [...tbody.querySelectorAll('tr')];
  rows.sort((a, b) => {
    const aVal = a.children[Array.from(th.closest('table').querySelectorAll('th')).findIndex(t => t.dataset.sort === key)].textContent;
    const bVal = b.children[Array.from(th.closest('table').querySelectorAll('th')).findIndex(t => t.dataset.sort === key)].textContent;
    const numA = parseFloat(aVal.replace(/[^0-9.-]/g, ''));
    const numB = parseFloat(bVal.replace(/[^0-9.-]/g, ''));
    let cmp;
    if (!isNaN(numA) && !isNaN(numB)) cmp = numA - numB;
    else cmp = aVal.localeCompare(bVal);
    return currentSort.dir === 'asc' ? cmp : -cmp;
  });
  rows.forEach(r => tbody.appendChild(r));
  thsForTable(th.closest('table')).forEach(t => t.classList.toggle('sorted', t.dataset.sort === key));
}

function thsForTable(table) {
  return table.querySelectorAll('th[data-sort]');
}

document.querySelectorAll('th[data-sort]').forEach(th => {
  th.addEventListener('click', handleSort);
});

// ── Charts ─────────────────────────────────────────────────────────

function renderModelChart(models) {
  const canvas = document.getElementById('chartModelDist');
  const ctx = canvas.getContext('2d');
  if (modelChart) modelChart.destroy();
  
  const labels = models.map(m => m.model.split('/').pop() || m.model);
  const inputData = models.map(m => m.total_input);
  const outputData = models.map(m => m.total_output);
  const cacheData = models.map(m => m.total_cache_read);
  
  modelChart = new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels: labels,
      datasets: [{
        label: 'Input',
        data: inputData,
        backgroundColor: '#f0883e',
        borderColor: '#0d1117',
        borderWidth: 2,
      }, {
        label: 'Output',
        data: outputData,
        backgroundColor: '#3fb950',
        borderColor: '#0d1117',
        borderWidth: 2,
      }, {
        label: 'Cache Read',
        data: cacheData,
        backgroundColor: '#a371f7',
        borderColor: '#0d1117',
        borderWidth: 2,
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { position: 'bottom', labels: { color: '#8b949e', padding: 12, font: { size: 11 } } },
        tooltip: {
          callbacks: {
            label: function(ctx) {
              const total = ctx.dataset.data.reduce((a,b) => a+b, 0);
              const pct = total > 0 ? ((ctx.parsed / total) * 100).toFixed(1) : 0;
              return ctx.label + ': ' + fmtNum(ctx.parsed) + ' (' + pct + '%)';
            }
          }
        }
      }
    }
  });
}

function renderStackedChart(models) {
  const canvas = document.getElementById('chartStacked');
  const ctx = canvas.getContext('2d');
  if (stackedChart) stackedChart.destroy();
  
  const labels = models.map(m => m.model.split('/').pop() || m.model);
  
  stackedChart = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: labels,
      datasets: [
        { label: 'Input', data: models.map(m => m.total_input), backgroundColor: '#f0883e', borderRadius: 3 },
        { label: 'Output', data: models.map(m => m.total_output), backgroundColor: '#3fb950', borderRadius: 3 },
        { label: 'Cache Read', data: models.map(m => m.total_cache_read), backgroundColor: '#a371f7', borderRadius: 3 },
        { label: 'Reasoning', data: models.map(m => m.total_reasoning), backgroundColor: '#d29922', borderRadius: 3 },
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        x: { ticks: { color: '#8b949e', font: { size: 10 } }, grid: { color: '#21262d' } },
        y: { ticks: { color: '#8b949e', font: { size: 10 }, callback: v => fmtNum(v) }, grid: { color: '#21262d' } }
      },
      plugins: {
        legend: { position: 'bottom', labels: { color: '#8b949e', padding: 12, font: { size: 11 } } },
        tooltip: {
          callbacks: {
            label: ctx => ctx.dataset.label + ': ' + fmtNum(ctx.parsed.y)
          }
        }
      }
    }
  });
}

function renderTimelineChart(timeline) {
  const canvas = document.getElementById('chartTimeline');
  const ctx = canvas.getContext('2d');
  if (timelineChart) timelineChart.destroy();
  
  const labels = timeline.map(t => t.hour_human);
  
  timelineChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels: labels,
      datasets: [
        { label: 'Input', data: timeline.map(t => t.input), borderColor: '#f0883e', backgroundColor: 'rgba(240,136,62,0.1)', fill: true, tension: 0.3, pointRadius: 2 },
        { label: 'Cache Read', data: timeline.map(t => t.cache_read), borderColor: '#a371f7', backgroundColor: 'rgba(163,113,247,0.1)', fill: true, tension: 0.3, pointRadius: 2 },
        { label: 'Output', data: timeline.map(t => t.output), borderColor: '#3fb950', backgroundColor: 'rgba(63,185,80,0.1)', fill: true, tension: 0.3, pointRadius: 2 },
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        x: { ticks: { color: '#8b949e', font: { size: 9 }, maxTicksLimit: 12 }, grid: { color: '#21262d' }, title: { color: '#8b949e', display: true, text: 'Hour' } },
        y: { ticks: { color: '#8b949e', font: { size: 10 }, callback: v => fmtNum(v) }, grid: { color: '#21262d' }, title: { color: '#8b949e', display: true, text: 'Tokens' } }
      },
      plugins: {
        legend: { position: 'bottom', labels: { color: '#8b949e', padding: 12, font: { size: 11 } } },
        tooltip: {
          callbacks: {
            label: ctx => ctx.dataset.label + ': ' + fmtNum(ctx.parsed.y) + ' @ ' + ctx.label
          }
        }
      },
      interaction: { intersect: false, mode: 'index' }
    }
  });
}

// ── Active sessions ────────────────────────────────────────────────
function renderActiveSessions(active) {
  const panel = document.getElementById('activePanel');
  const list = document.getElementById('activeList');
  const count = document.getElementById('activeCount');
  
  if (!active || active.length === 0) {
    panel.style.display = 'none';
    return;
  }
  panel.style.display = 'block';
  count.textContent = active.length;
  
  list.innerHTML = active.map(s => `
    <div class="alert info" style="cursor:pointer" onclick="openSessionModal('${s.id}')">
      <div class="alert-title">${s.display_label || s.platform} · ${s.model || 'unknown'}</div>
      Running for <strong>${s.age_human}</strong> · ${fmtInt(s.input_tokens)} input · ${fmtInt(s.output_tokens)} output · ${s.message_count || 0} messages
      ${s.last_activity_description ? '<br><span style="font-size:11px">Last: ' + s.last_activity_description + '</span>' : ''}
    </div>
  `).join('');
}

// ── Session modal ──────────────────────────────────────────────────
function openSessionModal(sessionId) {
  const modal = document.getElementById('sessionModal');
  const body = document.getElementById('modalBody');
  const title = document.getElementById('modalTitle');
  
  const s = allSessionData.find(d => d.session_id === sessionId);
  if (!s) return;
  
  title.textContent = 'Session: ' + sessionId.slice(-30);
  
  const limit = s.context_limit || 0;
  const pct = s.utilization_pct || 0;
  
  body.innerHTML = `
    <table style="width:100%;font-size:13px;margin-bottom:16px">
      <tr><td style="color:var(--muted);width:140px">Session ID</td><td><code style="font-size:11px">${s.session_id}</code></td></tr>
      <tr><td style="color:var(--muted)">Display</td><td>${s.display_name || '—'}</td></tr>
      <tr><td style="color:var(--muted)">Platform</td><td>${s.platform}</td></tr>
      <tr><td style="color:var(--muted)">Model</td><td><code style="color:var(--accent)">${s.model || '—'}</code></td></tr>
      <tr><td style="color:var(--muted)">Started</td><td>${s.first_seen_human || '—'}</td></tr>
      <tr><td style="color:var(--muted)">Ended</td><td>${s.last_seen_human || (s.duration_human ? 'active ' + s.duration_human : '—')}</td></tr>
      <tr><td style="color:var(--muted)">Duration</td><td>${s.duration_human || '—'}</td></tr>
      <tr><td style="color:var(--muted)">Messages</td><td>${fmtInt(s.message_count || 0)}</td></tr>
      <tr><td style="color:var(--muted)">Tool Calls</td><td>${fmtInt(s.tool_call_count || 0)}</td></tr>
      <tr><td style="color:var(--muted)">API Calls</td><td>${fmtInt(s.api_call_count || 0)}</td></tr>
    </table>
    
    <h3 style="font-size:14px;margin:16px 0 8px;color:var(--accent)">Token Breakdown</h3>
    <table style="width:100%;font-size:13px">
      <tr><td style="color:var(--muted);width:140px">Input Tokens</td><td class="num"><strong>${fmtInt(s.input_tokens)}</strong></td></tr>
      <tr><td style="color:var(--muted)">Output Tokens</td><td class="num"><strong>${fmtInt(s.output_tokens)}</strong></td></tr>
      <tr><td style="color:var(--muted)">Cache Read</td><td class="num">${fmtInt(s.cache_read_tokens)} (${s.cache_read_tokens > 0 ? (s.cache_read_tokens / (s.input_tokens || 1) * 100).toFixed(1) + '% of input' : '0%'})</td></tr>
      <tr><td style="color:var(--muted)">Cache Write</td><td class="num">${fmtInt(s.cache_write_tokens)}</td></tr>
      <tr><td style="color:var(--muted)">Reasoning</td><td class="num">${fmtInt(s.reasoning_tokens)}</td></tr>
      <tr><td style="color:var(--muted)">Total (In+Out)</td><td class="num" style="color:var(--accent)"><strong>${fmtInt(s.total_tokens)}</strong></td></tr>
      <tr><td style="color:var(--muted)">Context Limit</td><td class="num">${limit > 0 ? fmtInt(limit) + ' tokens' : 'unknown'}</td></tr>
      <tr><td style="color:var(--muted)">Cumulative Util.</td>
        <td class="num">
          ${limit > 0 ? `
            <span class="${pct > 100 ? 'status-danger' : pct > 50 ? 'status-warn' : 'status-ok'}">${pct.toFixed(1)}%</span>
            <div class="context-bar-wrap" style="margin-top:4px">
              <div class="context-bar-track"><div class="context-bar-fill ${pct > 100 ? 'danger' : pct > 50 ? 'warn' : 'safe'}" style="width:${Math.min(100,pct)}%"></div></div>
            </div>
            <div style="font-size:10px;color:var(--muted);margin-top:2px">Note: this is cumulative across ${s.api_call_count || 0} API calls. Individual calls respect the limit.</span>
          ` : 'unknown limit'}
        </td>
      </tr>
      <tr><td style="color:var(--muted)">Estimated Cost</td><td class="num">${s.estimated_cost_usd != null ? '$' + s.estimated_cost_usd.toFixed(4) : '—'}</td></tr>
      <tr><td style="color:var(--muted)">Cost Status</td><td>${s.cost_status || '—'}</td></tr>
      <tr><td style="color:var(--muted)">Model Config</td><td style="font-size:11px;color:var(--muted)">${s.model_config_preview || 'default'}</td></tr>
    </table>
    
    <div style="margin-top:16px;padding-top:12px;border-top:1px solid var(--border)">
      <button onclick="closeModal()" style="background:var(--surface);border:1px solid var(--border);color:var(--text);padding:8px 16px;border-radius:6px;cursor:pointer;font-family:inherit;font-size:13px">Close</button>
      <button onclick="refreshAll()" style="background:var(--accent);border:1px solid var(--accent);color:#0d1117;padding:8px 16px;border-radius:6px;cursor:pointer;font-family:inherit;font-size:13px;font-weight:600;margin-left:8px">⟳ Refresh Data</button>
    </div>
  `;
  
  modal.classList.add('active');
}

function closeModal() {
  document.getElementById('sessionModal').classList.remove('active');
}

// ── Main refresh ───────────────────────────────────────────────────
async function refreshAll() {
  try {
    const [summary, sessions, models, channels, timeline, active, alerts] = await Promise.all([
      api('/api/summary'),
      api('/api/sessions'),
      api('/api/models'),
      api('/api/channels'),
      api('/api/timeline'),
      api('/api/active'),
      api('/api/alerts'),
    ]);
    
    document.getElementById('lastUpdated').textContent = 'Updated: ' + new Date().toLocaleTimeString();
    document.getElementById('footerNote').textContent = 'Context limits: ' + CONTEXT_COUNT + ' models tracked';

    renderKPIs(summary);
    renderAlerts(alerts);
    renderModelTable(models);
    renderChannelTable(channels);
    renderSessionTable(sessions);
    renderModelChart(models);
    renderStackedChart(models);
    renderTimelineChart(timeline);
    renderActiveSessions(active);
    
  } catch (err) {
    console.error('Refresh failed:', err);
    document.getElementById('lastUpdated').textContent = 'Error: ' + err.message;
  }
}

// Initial load
refreshAll();
// Auto-refresh every 30 seconds
setInterval(refreshAll, 30000);
</script>
</body>
</html>
"""


class DashboardHandler(SimpleHTTPRequestHandler):
    """HTTP handler with API endpoints + embedded HTML."""
    
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        
        if path == '/' or path == '/index.html':
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Cache-Control', 'no-cache')
            self.end_headers()
            html = HTML_TEMPLATE
            context_json = json.dumps(CONTEXT_LIMITS)
            context_count = sum(1 for v in CONTEXT_LIMITS.values() if v > 0)
            html = html.replace('{{ CONTEXT_LIMITS_JSON }}', context_json)
            html = html.replace('{{ CONTEXT_COUNT }}', str(context_count))
            self.wfile.write(html.encode('utf-8'))
        
        elif path == '/api/summary':
            data = api_dashboard_summary()
            self.send_json(data)
        
        elif path == '/api/sessions':
            data = api_sessions_summary()
            self.send_json(data)
        
        elif path == '/api/models':
            data = api_model_aggregation()
            self.send_json(data)
        
        elif path == '/api/channels':
            data = api_channel_breakdown()
            self.send_json(data)
        
        elif path == '/api/timeline':
            data = api_token_timeline()
            self.send_json(data)
        
        elif path == '/api/active':
            data = api_active_sessions()
            self.send_json(data)
        
        elif path == '/api/alerts':
            data = api_alerts()
            self.send_json(data)
        
        elif path == '/api/full':
            data = {
                'summary': api_dashboard_summary(),
                'sessions': api_sessions_summary(),
                'models': api_model_aggregation(),
                'channels': api_channel_breakdown(),
                'timeline': api_token_timeline(),
                'active': api_active_sessions(),
                'alerts': api_alerts(),
            }
            self.send_json(data)
        
        elif path == '/health':
            self.send_json({'status': 'ok', 'db': DB_PATH, 'port': DASHBOARD_PORT})
        
        else:
            self.send_error(404, 'Not found')
    
    def send_json(self, data):
        body = json.dumps(data, default=str, indent=2 if self.path == '/api/full' else None)
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Cache-Control', 'no-cache')
        self.end_headers()
        self.wfile.write(body.encode('utf-8'))
    
    def log_message(self, format, *args):
        # Quiet logging
        pass


def run_server(port=DASHBOARD_PORT, open_browser=False):
    server = ThreadingHTTPServer(('127.0.0.1', port), DashboardHandler)
    print(f"\n{'='*60}")
    print(f"  Hermes Token Dashboard")
    print(f"{'='*60}")
    print(f"  URL:        http://127.0.0.1:{port}")
    print(f"  Data from:  {DB_PATH}")
    print(f"  Port:       {port}")
    print(f"{'='*60}\n")
    
    if open_browser:
        import webbrowser
        threading.Timer(1.5, lambda: webbrowser.open(f'http://127.0.0.1:{port}')).start()
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.shutdown()


if __name__ == '__main__':
    port = DASHBOARD_PORT
    open_browser = False
    
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == '--port' and i + 1 < len(args):
            port = int(args[i + 1])
            i += 2
        elif args[i] == '--browser':
            open_browser = True
            i += 1
        elif args[i] == '-p' and i + 1 < len(args):
            port = int(args[i + 1])
            i += 2
        else:
            i += 1
    
    run_server(port, open_browser)
