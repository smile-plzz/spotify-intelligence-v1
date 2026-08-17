#!/usr/bin/env python3
"""
Hermes Command Center — Alfred Intelligence Dashboard Server
Extends the existing token_dashboard.py with Alfred Intelligence endpoints
and a command-center frontend.

Usage:
    python3 command_center.py              # port 8770
    python3 command_center.py --port 9000 # custom port
    python3 command_center.py --browser   # auto-open browser
"""

import json
import os
import sqlite3
import sys
import time
import datetime
import threading
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse

# Import intelligence engine
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import alfred_intelligence as ai

# Reuse DB path and context limits from intelligence engine
DB_PATH = ai.DB_PATH
CONTEXT_LIMITS = ai.CONTEXT_LIMITS
DASHBOARD_PORT = int(os.environ.get("DASHBOARD_PORT", 8770))


# ── Lightweight API endpoints (mirroring existing dashboard for compatibility) ──

def api_dashboard_summary():
    return ai.db_query_one("""
        SELECT 
            COUNT(*) as request_files,
            SUM(input_tokens) as total_input,
            SUM(output_tokens) as total_output,
            SUM(cache_read_tokens) as total_cache_read,
            SUM(cache_write_tokens) as total_cache_write,
            SUM(reasoning_tokens) as total_reasoning,
            SUM(api_call_count) as total_calls,
            COUNT(DISTINCT session_id) as unique_sessions
        FROM session_model_usage
    """) or {}


def api_sessions_summary():
    rows = ai.db_query("""
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
        r["context_limit"] = ai.get_context_limit(r["model"])
        r["utilization_pct"] = (
            round((r["input_tokens"] / r["context_limit"]) * 100, 2)
            if r["context_limit"] > 0 else 0
        )
        r["total_tokens"] = r["input_tokens"] + r["output_tokens"]
        start = r.get("started_at") or 0
        end = r.get("last_seen") or time.time()
        r["duration_seconds"] = max(0, end - start)
        r["duration_human"] = ai.format_duration(r["duration_seconds"])
        r["first_seen_human"] = ai.fmt_ts(r["first_seen"])
        r["last_seen_human"] = ai.fmt_ts(r["last_seen"])
        if not r.get("display_name") and r.get("session_key"):
            r["display_name"] = ai.infer_display(r["session_key"])
        r["platform"] = ai.infer_platform(r.get("session_key", ""))
        r["model_config_preview"] = ai.preview_config(r.get("model_config"))
    return rows


def api_model_aggregation():
    rows = ai.db_query("""
        SELECT 
            model,
            billing_provider,
            COUNT(DISTINCT session_id) as sessions,
            SUM(api_call_count) as total_calls,
            SUM(input_tokens) as total_input,
            SUM(output_tokens) as total_output,
            SUM(cache_read_tokens) as total_cache_read,
            SUM(cache_write_tokens) as total_cache_write,
            SUM(reasoning_tokens) as total_reasoning
        FROM session_model_usage
        GROUP BY model, billing_provider
        ORDER BY total_input DESC
    """)
    for r in rows:
        r["context_limit"] = ai.get_context_limit(r["model"])
        r["total_tokens"] = r["total_input"] + r["total_output"]
        r["cache_pct"] = (
            round((r["total_cache_read"] / r["total_input"]) * 100, 2)
            if r["total_input"] > 0 else 0
        )
        r["input_share_pct"] = 0
    total_input = sum(r["total_input"] for r in rows) or 1
    for r in rows:
        r["input_share_pct"] = round((r["total_input"] / total_input) * 100, 2)
    return rows


def api_channel_breakdown():
    rows = ai.db_query("""
        SELECT 
            s.session_key,
            s.display_name,
            su.model,
            su.input_tokens,
            su.output_tokens,
            su.cache_read_tokens,
            su.message_count,
            su.api_call_count,
            su.first_seen,
            su.last_seen,
            COUNT(DISTINCT su.session_id) as usage_rows
        FROM session_model_usage su
        JOIN sessions s ON su.session_id = s.id
        GROUP BY s.session_key, s.display_name, su.model
        ORDER BY su.input_tokens DESC
    """)
    from collections import defaultdict
    agg = defaultdict(lambda: {
        "platform": "", "display_label": "", "sessions": 0,
        "input_tokens": 0, "output_tokens": 0, "cache_read": 0,
        "messages": 0, "api_calls": 0, "total_tokens": 0,
        "duration_seconds": 0
    })
    for r in rows:
        platform = ai.infer_platform(r["session_key"] or "")
        display_label = r["display_name"] or ai.infer_display(r["session_key"] or "")
        if not display_label or display_label == "---":
            display_label = platform
        key = (platform, display_label)
        a = agg[key]
        a["platform"] = platform
        a["display_label"] = display_label or platform
        a["sessions"] += 1
        a["input_tokens"] += r["input_tokens"] or 0
        a["output_tokens"] += r["output_tokens"] or 0
        a["cache_read"] += r["cache_read_tokens"] or 0
        a["messages"] += r["message_count"] or 0
        a["api_calls"] += r["usage_rows"]
        a["total_tokens"] += (r["input_tokens"] or 0) + (r["output_tokens"] or 0)
        a["duration_seconds"] += max(0, (r["last_seen"] or time.time()) - (r["first_seen"] or 0))
    result = list(agg.values())
    total_in = sum(a["input_tokens"] for a in result) or 1
    for a in result:
        a["input_share_pct"] = round((a["input_tokens"] / total_in) * 100, 2)
        a["duration_human"] = ai.format_duration(a["duration_seconds"])
    result.sort(key=lambda x: -x["input_tokens"])
    return result


def api_token_timeline():
    rows = ai.db_query("""
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
    buckets = {}
    for r in rows:
        ts = r["first_seen"]
        hour_key = int(ts / 3600) * 3600
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
    rows = ai.db_query("""
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
            r["display_name"] = ai.infer_display(sk)
        r["platform"] = ai.infer_platform(sk)
        r["display_label"] = r["display_name"] or ai.infer_display(sk) or "Unknown"
        r["age_seconds"] = time.time() - (r.get("started_at") or 0)
        r["age_human"] = ai.format_duration(r["age_seconds"])
    return rows


def api_alerts():
    alerts = []
    smu = ai.db_query("""
        SELECT session_id, model, input_tokens, output_tokens,
               api_call_count, first_seen, last_seen
        FROM session_model_usage
        ORDER BY input_tokens DESC
        LIMIT 20
    """)
    for r in smu:
        limit = ai.get_context_limit(r["model"])
        pct = (r["input_tokens"] / limit * 100) if limit > 0 else 0
        if pct > 100:
            alerts.append({
                "level": "warning",
                "type": "high_cumulative_tokens",
                "msg": f"Session {r['session_id'][-20:]} with {r['model']} has {r['input_tokens']:,} cumulative input tokens — {pct:.0f}% of {limit:,} context limit (across {r['api_call_count']} API calls).",
                "session_id": r["session_id"],
                "model": r["model"],
                "input_tokens": r["input_tokens"],
                "utilization_pct": round(pct, 1),
                "context_limit": limit,
            })
    orphaned = ai.db_query("""
        SELECT id, session_key, display_name, model, started_at, input_tokens
        FROM sessions
        WHERE (ended_at = 0 OR ended_at IS NULL)
          AND started_at < (strftime('%s','now') - 3600)
        ORDER BY started_at ASC
    """)
    now = time.time()
    for r in orphaned:
        age = (now - (r["started_at"] or 0)) if r["started_at"] else 0
        sk = r.get("session_key") or ""
        label = r.get("display_name") or (sk[-30:] if sk else (r.get("id") or "unknown")[-30:])
        alerts.append({
            "level": "info",
            "type": "orphaned_session",
            "msg": f"Session '{label}' started {ai.format_duration(age)} ago with no end time. Input tokens: {r['input_tokens']:,}.",
            "session_id": r["id"],
            "age_seconds": age,
        })
    dump_errors = ai.db_query("SELECT COUNT(*) as cnt FROM sessions WHERE input_tokens > 0 AND message_count = 0")
    return alerts


# ── HTTP Handler ─────────────────────────────────────────────────────

class CommandCenterHandler(SimpleHTTPRequestHandler):
    server_port = DASHBOARD_PORT  # updated by run_server

    def do_GET(self):
        try:
            parsed = urlparse(self.path)
            path = parsed.path

            if path == '/' or path == '/index.html':
                self.send_html()
            elif path == '/api/intelligence':
                self.send_json(ai.compute_all_intelligence())
            elif path == '/api/summary':
                self.send_json(ai.db_query_one("""
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
                """) or {})
            elif path == '/api/sessions':
                self.send_json(api_sessions_summary())
            elif path == '/api/models':
                self.send_json(api_model_aggregation())
            elif path == '/api/channels':
                self.send_json(api_channel_breakdown())
            elif path == '/api/timeline':
                self.send_json(api_token_timeline())
            elif path == '/api/active':
                self.send_json(api_active_sessions())
            elif path == '/api/alerts':
                self.send_json(api_alerts())
            elif path == '/api/full':
                self.send_json({
                    'summary': api_dashboard_summary(),
                    'sessions': api_sessions_summary(),
                    'models': api_model_aggregation(),
                    'channels': api_channel_breakdown(),
                    'timeline': api_token_timeline(),
                    'active': api_active_sessions(),
                    'alerts': api_alerts(),
                })
            elif path == '/health':
                port = getattr(self.server, 'server_address', (None, None))[1] or 8770
                self.send_json({'status': 'ok', 'db': DB_PATH, 'port': port})
            else:
                self.send_error(404, 'Not found')
        except Exception as e:
            import traceback
            traceback.print_exc()
            try:
                self.send_error(500, f'Server error: {e}')
            except:
                pass

    def send_html(self):
        html = HTML_TEMPLATE
        context_json = json.dumps(CONTEXT_LIMITS)
        context_count = sum(1 for v in CONTEXT_LIMITS.values() if v > 0)
        html = html.replace('{{ CONTEXT_LIMITS_JSON }}', context_json)
        html = html.replace('{{ CONTEXT_COUNT }}', str(context_count))
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Cache-Control', 'no-cache')
        self.end_headers()
        self.wfile.write(html.encode('utf-8'))

    def send_json(self, data):
        body = json.dumps(data, default=str, indent=2 if self.path == '/api/full' or self.path == '/api/intelligence' else None)
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Cache-Control', 'no-cache')
        self.end_headers()
        self.wfile.write(body.encode('utf-8'))

    def log_message(self, format, *args):
        pass


# ── HTML Template ────────────────────────────────────────────────────

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Hermes Command Center — Alfred Intelligence</title>
<style>
  :root {
    --bg: #0a0c0f;
    --surface: #111318;
    --surface-2: #161a20;
    --border: #1e2229;
    --border-soft: #1a1d23;
    --text: #e2e4e8;
    --text-muted: #6b7178;
    --text-dim: #4a4f57;
    --critical: #ef4444;
    --critical-bg: rgba(239,68,68,0.08);
    --warning: #f59e0b;
    --warning-bg: rgba(245,158,11,0.08);
    --optimization: #eab308;
    --optimization-bg: rgba(234,179,8,0.06);
    --healthy: #22c55e;
    --healthy-bg: rgba(34,197,94,0.06);
    --info: #3b82f6;
    --info-bg: rgba(59,130,246,0.06);
    --accent: #f97316;
    --accent-dim: rgba(249,115,22,0.15);
    --grid-line: #14171c;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  html { font-size: 14px; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', sans-serif;
    background: var(--bg);
    color: var(--text);
    min-height: 100vh;
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
  }
  .container { max-width: 1480px; margin: 0 auto; padding: 0 24px; }

  /* ── Typography ── */
  .h1 { font-size: 20px; font-weight: 600; letter-spacing: -0.01em; line-height: 1.3; }
  .h2 { font-size: 13px; font-weight: 600; letter-spacing: 0.02em; text-transform: uppercase; color: var(--text-muted); margin-bottom: 12px; }
  .h3 { font-size: 12px; font-weight: 500; color: var(--text-muted); }
  .body { font-size: 13px; line-height: 1.55; }
  .mono { font-family: 'SF Mono', 'JetBrains Mono', 'Fira Code', monospace; font-variant-numeric: tabular-nums; }
  .dim { color: var(--text-dim); }
  .muted { color: var(--text-muted); }

  /* ── Layout ── */
  .section { margin-bottom: 28px; }
  .section-inner {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 20px;
  }

  /* ── Grid ── */
  .grid-4 { display: grid; grid-template-columns: repeat(4, 1fr); gap: 1px; background: var(--border-soft); border: 1px solid var(--border-soft); border-radius: 6px; overflow: hidden; }
  .grid-3 { display: grid; grid-template-columns: repeat(3, 1fr); gap: 1px; background: var(--border-soft); border: 1px solid var(--border-soft); border-radius: 6px; overflow: hidden; }
  .grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 1px; background: var(--border-soft); border-bottom: 1px solid var(--border-soft); }
  .grid-2-1 { display: grid; grid-template-columns: 2fr 1fr; gap: 1px; background: var(--border-soft); border-bottom: 1px solid var(--border-soft); }
  .grid-1-2 { display: grid; grid-template-columns: 1fr 2fr; gap: 1px; background: var(--border-soft); border-bottom: 1px solid var(--border-soft); }

  /* ── Cells ── */
  .cell { background: var(--surface); padding: 16px 18px; min-width: 0; }
  .cell.accent { border-left: 2px solid var(--accent); }
  .cell.critical { border-left: 2px solid var(--critical); }
  .cell.warning { border-left: 2px solid var(--warning); }
  .cell.healthy { border-left: 2px solid var(--healthy); }
  .cell.info { border-left: 2px solid var(--info); }

  .kpi-label { font-size: 10px; text-transform: uppercase; letter-spacing: 0.06em; color: var(--text-muted); margin-bottom: 4px; }
  .kpi-value { font-size: 22px; font-weight: 600; letter-spacing: -0.02em; line-height: 1.1; }
  .kpi-sub { font-size: 11px; color: var(--text-muted); margin-top: 2px; }
  .kpi-delta { font-size: 11px; margin-top: 2px; }

  /* ── Status indicators ── */
  .status-dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 6px; vertical-align: middle; }
  .status-dot.green { background: var(--healthy); box-shadow: 0 0 6px rgba(34,197,94,0.4); }
  .status-dot.orange { background: var(--warning); box-shadow: 0 0 6px rgba(245,158,11,0.4); }
  .status-dot.red { background: var(--critical); box-shadow: 0 0 6px rgba(239,68,68,0.4); }

  /* ── Section headers ── */
  .section-header {
    display: flex; align-items: center; justify-content: space-between;
    margin-bottom: 16px; padding-bottom: 12px;
    border-bottom: 1px solid var(--border);
  }
  .section-header .h2 { margin-bottom: 0; }
  .section-header .badge {
    font-size: 10px; padding: 2px 8px; border-radius: 10px;
    background: var(--surface-2); color: var(--text-muted);
    border: 1px solid var(--border);
  }

  /* ── Alfred Intelligence Panel ── */
  .alfred-panel {
    background: linear-gradient(180deg, var(--surface) 0%, var(--surface-2) 100%);
    border: 1px solid var(--accent-dim);
    border-radius: 6px;
    padding: 20px;
    position: relative;
    overflow: hidden;
  }
  .alfred-panel::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0; height: 1px;
    background: linear-gradient(90deg, transparent, var(--accent), transparent);
    opacity: 0.5;
  }
  .alfred-label {
    font-size: 10px; text-transform: uppercase; letter-spacing: 0.08em;
    color: var(--accent); margin-bottom: 8px;
    display: flex; align-items: center; gap: 6px;
  }
  .alfred-label::before {
    content: '';
    width: 6px; height: 6px; border-radius: 50%;
    background: var(--accent);
    box-shadow: 0 0 8px rgba(249,115,22,0.5);
  }
  .alfred-name { font-size: 14px; font-weight: 600; color: var(--text); margin-bottom: 12px; }
  .alfred-assessment {
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 14px 16px;
    margin-bottom: 14px;
  }
  .alfred-assessment-row {
    display: flex; gap: 4px; align-items: baseline; margin-bottom: 4px;
    font-size: 13px; line-height: 1.5;
  }
  .alfred-label-small {
    font-size: 10px; text-transform: uppercase; letter-spacing: 0.05em;
    color: var(--text-muted); width: 100px; flex-shrink: 0;
    padding-top: 1px;
  }
  .alfred-value { color: var(--text); flex: 1; }
  .alfred-value.fact { color: var(--healthy); }
  .alfred-value.analysis { color: var(--warning); }
  .alfred-value.interpretation { color: var(--text); font-style: italic; }
  .alfred-value.recommendation { color: var(--accent); font-weight: 500; }

  .fact-tag { display: inline-block; font-size: 9px; text-transform: uppercase; letter-spacing: 0.04em; padding: 1px 5px; border-radius: 3px; margin-right: 4px; vertical-align: middle; }
  .fact-tag.fact { background: rgba(34,197,94,0.12); color: var(--healthy); }
  .fact-tag.analysis { background: rgba(245,158,11,0.12); color: var(--warning); }
  .fact-tag.interpretation { background: rgba(59,130,246,0.12); color: var(--info); }
  .fact-tag.recommendation { background: rgba(249,115,22,0.12); color: var(--accent); }

  /* ── Insight cards ── */
  .insight-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 14px 16px;
    margin-bottom: 10px;
    cursor: pointer;
    transition: border-color 0.12s;
  }
  .insight-card:hover { border-color: var(--accent-dim); }
  .insight-card.selected { border-color: var(--accent); background: var(--surface-2); }
  .insight-card-header {
    display: flex; align-items: flex-start; gap: 8px;
    margin-bottom: 6px;
  }
  .insight-severity {
    width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0;
    margin-top: 4px;
  }
  .insight-severity.warning { background: var(--warning); box-shadow: 0 0 4px rgba(245,158,11,0.3); }
  .insight-severity.healthy { background: var(--healthy); box-shadow: 0 0 4px rgba(34,197,94,0.3); }
  .insight-severity.info { background: var(--info); box-shadow: 0 0 4px rgba(59,130,246,0.3); }
  .insight-category {
    font-size: 10px; text-transform: uppercase; letter-spacing: 0.04em;
    color: var(--text-muted); margin-left: auto; flex-shrink: 0;
  }
  .insight-observation { font-size: 13px; font-weight: 500; line-height: 1.4; margin-bottom: 4px; }
  .insight-evidence { font-size: 11px; color: var(--text-muted); line-height: 1.5; margin-bottom: 6px; padding-left: 12px; border-left: 2px solid var(--border); }
  .insight-interpretation { font-size: 12px; color: var(--text); line-height: 1.5; margin-bottom: 4px; }
  .insight-impact { font-size: 11px; color: var(--text-muted); line-height: 1.4; margin-bottom: 6px; }
  .insight-decision {
    font-size: 12px; color: var(--accent); line-height: 1.4;
    padding: 8px 10px; background: var(--accent-dim); border-radius: 3px;
    margin-top: 4px;
  }
  .insight-decision strong { font-weight: 600; }

  /* ── Attention required ── */
  .attention-item {
    display: flex; gap: 10px; align-items: flex-start;
    padding: 10px 12px; margin-bottom: 4px;
    border-radius: 4px; cursor: pointer;
    transition: background 0.1s;
  }
  .attention-item:hover { background: var(--surface-2); }
  .attention-item.selected { background: var(--surface-2); }
  .attention-icon {
    width: 28px; height: 28px; border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    font-size: 13px; flex-shrink: 0; margin-top: 1px;
  }
  .attention-icon.critical { background: var(--critical-bg); color: var(--critical); }
  .attention-icon.warning { background: var(--warning-bg); color: var(--warning); }
  .attention-icon.optimization { background: var(--optimization-bg); color: var(--optimization); }
  .attention-icon.healthy { background: var(--healthy-bg); color: var(--healthy); }
  .attention-icon.info { background: var(--info-bg); color: var(--info); }
  .attention-content { flex: 1; min-width: 0; }
  .attention-title { font-size: 13px; font-weight: 500; margin-bottom: 2px; }
  .attention-desc { font-size: 11px; color: var(--text-muted); line-height: 1.4; }
  .attention-meta { display: flex; gap: 8px; margin-top: 4px; font-size: 10px; color: var(--text-dim); }
  .attention-meta span { display: flex; align-items: center; gap: 3px; }
  .attention-meta .label { color: var(--text-muted); }

  /* ── Decision queue ── */
  .decision-item {
    display: flex; gap: 12px; align-items: flex-start;
    padding: 12px 14px; margin-bottom: 6px;
    border: 1px solid var(--border);
    border-radius: 4px; cursor: pointer;
    transition: all 0.12s;
  }
  .decision-item:hover { border-color: var(--accent-dim); background: var(--surface-2); }
  .decision-priority {
    font-size: 20px; line-height: 1; flex-shrink: 0; margin-right: 4px;
    margin-top: 1px;
  }
  .decision-body { flex: 1; min-width: 0; }
  .decision-title { font-size: 13px; font-weight: 500; margin-bottom: 3px; }
  .decision-why { font-size: 11px; color: var(--text-muted); line-height: 1.45; margin-bottom: 5px; }
  .decision-action {
    font-size: 11px; padding: 6px 8px; border-radius: 3px;
    background: var(--surface-2); border: 1px solid var(--border);
  }
  .decision-action.critical { border-color: var(--critical); color: var(--critical); }
  .decision-action.warning { border-color: var(--warning); color: var(--warning); }
  .decision-action.optimization { border-color: var(--optimization); color: var(--optimization); }
  .decision-action.healthy { border-color: var(--healthy); color: var(--healthy); }
  .decision-action .action-label { font-weight: 600; text-transform: uppercase; letter-spacing: 0.04em; font-size: 9px; margin-bottom: 2px; }

  /* ── What Changed ── */
  .change-row {
    display: flex; gap: 16px; align-items: center;
    padding: 8px 0; border-bottom: 1px solid var(--grid-line);
  }
  .change-row:last-child { border-bottom: none; }
  .change-metric { font-size: 12px; color: var(--text); width: 140px; flex-shrink: 0; }
  .change-values { flex: 1; font-size: 11px; color: var(--text-muted); }
  .change-delta {
    font-size: 14px; font-weight: 600; width: 80px; text-align: right;
    font-family: 'SF Mono', 'JetBrains Mono', monospace;
  }
  .change-delta.up { color: var(--warning); }
  .change-delta.down { color: var(--healthy); }
  .change-delta.stable { color: var(--text-dim); }

  /* ── Activity timeline ── */
  .timeline-item {
    display: flex; gap: 10px; align-items: flex-start;
    padding: 6px 0; border-bottom: 1px solid var(--grid-line);
    cursor: pointer; transition: background 0.1s;
  }
  .timeline-item:hover { background: var(--surface-2); padding-left: 4px; border-radius: 2px; }
  .timeline-item:last-child { border-bottom: none; }
  .timeline-time {
    font-size: 11px; color: var(--text-dim); width: 48px; flex-shrink: 0;
    font-family: 'SF Mono', 'JetBrains Mono', monospace;
  }
  .timeline-content { flex: 1; min-width: 0; }
  .timeline-title { font-size: 12px; color: var(--text); }
  .timeline-desc { font-size: 11px; color: var(--text-muted); line-height: 1.4; }
  .timeline-tags { display: flex; gap: 4px; margin-top: 2px; }
  .timeline-tag { font-size: 9px; padding: 1px 4px; border-radius: 2px; background: var(--surface-2); color: var(--text-dim); border: 1px solid var(--border); }

  /* ── Briefing box ── */
  .briefing-box {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 14px 16px;
    margin-bottom: 8px;
  }
  .briefing-row {
    display: flex; gap: 8px; align-items: baseline; font-size: 12px;
    padding: 2px 0;
  }
  .briefing-label { color: var(--text-muted); width: 120px; flex-shrink: 0; font-size: 11px; }
  .briefing-value { color: var(--text); flex: 1; }

  /* ── Drill-down detail panel ── */
  .detail-panel {
    background: var(--surface);
    border: 1px solid var(--accent-dim);
    border-radius: 4px;
    padding: 14px 16px;
    margin-top: 12px;
    display: none;
  }
  .detail-panel.active { display: block; animation: fadeIn 0.12s ease; }
  @keyframes fadeIn { from { opacity: 0; transform: translateY(-2px); } to { opacity: 1; transform: translateY(0); } }
  .detail-row {
    display: flex; gap: 12px; padding: 4px 0; font-size: 12px;
    border-bottom: 1px solid var(--grid-line);
  }
  .detail-row:last-child { border-bottom: none; }
  .detail-label { color: var(--text-muted); width: 120px; flex-shrink: 0; font-size: 11px; }
  .detail-value { color: var(--text); flex: 1; font-family: 'SF Mono', 'JetBrains Mono', monospace; font-size: 11px; }

  /* ── Utility ── */
  .flex-between { display: flex; justify-content: space-between; align-items: center; }
  .gap-8 { gap: 8px; }
  .gap-4 { gap: 4px; }
  .mt-8 { margin-top: 8px; }
  .mt-4 { margin-top: 4px; }
  .mb-4 { margin-bottom: 4px; }
  .mb-8 { margin-bottom: 8px; }
  .text-center { text-align: center; }
  .text-right { text-align: right; }
  .truncate { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .flex { display: flex; }
  .flex-col { display: flex; flex-direction: column; }
  .items-center { align-items: center; }

  /* ── Empty states ── */
  .empty-state {
    text-align: center; padding: 32px; color: var(--text-dim);
    font-size: 12px;
  }

  /* ── Indicators bar ── */
  .indicators {
    display: flex; gap: 16px; flex-wrap: wrap; padding: 4px 0;
  }
  .indicator {
    display: flex; align-items: center; gap: 5px;
    font-size: 11px; color: var(--text-muted);
  }
  .indicator .dot { width: 6px; height: 6px; border-radius: 50%; }
  .indicator .dot.green { background: var(--healthy); }
  .indicator .dot.orange { background: var(--warning); }
  .indicator .dot.red { background: var(--critical); }
  .indicator .dot.dim { background: var(--text-dim); }

  /* ── Scrollbar ── */
  ::-webkit-scrollbar { width: 6px; height: 6px; }
  ::-webkit-scrollbar-track { background: var(--bg); }
  ::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }
  ::-webkit-scrollbar-thumb:hover { background: var(--text-dim); }

  /* ── Responsive ── */
  @media (max-width: 1100px) {
    .grid-4 { grid-template-columns: repeat(2, 1fr); }
    .grid-3 { grid-template-columns: repeat(2, 1fr); }
    .grid-2-1, .grid-1-2 { grid-template-columns: 1fr; }
  }
  @media (max-width: 700px) {
    .grid-4, .grid-3, .grid-2 { grid-template-columns: 1fr; }
    .container { padding: 0 12px; }
  }
</style>
</head>
<body>
<div class="container">

  <!-- ════════ HEADER ════════ -->
  <div class="section" style="margin-bottom: 8px;">
    <div class="flex-between">
      <div>
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:2px;">
          <span style="font-size:18px;">⚙</span>
          <span class="h1">Hermes Command Center</span>
        </div>
        <div class="muted" style="font-size:12px;">Alfred Intelligence · Operational oversight for your Hermes system</div>
      </div>
      <div class="flex gap-4 items-center">
        <span class="muted" style="font-size:11px;" id="systemTime"></span>
        <button onclick="refreshAll()" style="background:var(--surface);border:1px solid var(--border);color:var(--text);padding:6px 12px;border-radius:4px;cursor:pointer;font-size:11px;font-family:inherit;">⟳ Refresh</button>
      </div>
    </div>
  </div>

  <!-- ════════ SYSTEM STATUS ════════ -->
  <div class="section">
    <div class="grid-4" id="statusGrid">
      <!-- Filled by JS -->
    </div>
  </div>

  <!-- ════════ ALFRED INTELLIGENCE ════════ -->
  <div class="section" id="alfredSection">
    <div class="alfred-panel">
      <div class="alfred-label">Alfred Intelligence</div>
      <div class="alfred-name">System Assessment</div>
      <div id="alfredAssessment" class="alfred-assessment"></div>
      <div style="margin-top:8px;">
        <div class="h3" style="margin-bottom:6px;">Alfred's Insights</div>
        <div id="alfredInsights"></div>
      </div>
    </div>
  </div>

  <!-- ════════ WHAT CHANGED ════════ -->
  <div class="section">
    <div class="section-inner">
      <div class="section-header">
        <div class="h2">What Changed — Since Last Period</div>
        <span class="badge" id="changeBadge">0 changes</span>
      </div>
      <div id="whatChanged"></div>
      <div id="whatChangedDetail" class="detail-panel"></div>
    </div>
  </div>

  <!-- ════════ ATTENTION REQUIRED ════════ -->
  <div class="section">
    <div class="section-inner">
      <div class="section-header">
        <div class="h2">Attention Required</div>
        <div class="flex gap-8 items-center">
          <span class="badge" style="border-color:var(--critical);color:var(--critical);" id="critCount">0</span>
          <span class="badge" style="border-color:var(--warning);color:var(--warning);" id="warnCount">0</span>
          <span class="badge" style="border-color:var(--optimization);color:var(--optimization);" id="optCount">0</span>
          <span class="badge" style="border-color:var(--healthy);color:var(--healthy);" id="healthyCount">0</span>
          <span class="badge" style="border-color:var(--info);color:var(--info);" id="infoCount">0</span>
        </div>
      </div>
      <div id="attentionList"></div>
      <div id="attentionDetail" class="detail-panel"></div>
    </div>
  </div>

  <!-- ════════ DECISION QUEUE ════════ -->
  <div class="section">
    <div class="section-inner">
      <div class="section-header">
        <div class="h2">Decision Queue</div>
        <span class="badge" id="decisionCount">0 decisions</span>
      </div>
      <div id="decisionQueue"></div>
      <div id="decisionDetail" class="detail-panel"></div>
    </div>
  </div>

  <!-- ════════ DAILY BRIEFING ════════ -->
  <div class="section">
    <div class="section-inner">
      <div class="section-header">
        <div class="h2">Alfred's Daily Briefing</div>
        <span class="badge">periodic summary</span>
      </div>
      <div id="dailyBriefing"></div>
    </div>
  </div>

  <!-- ════════ ANOMALIES ════════ -->
  <div class="section">
    <div class="section-inner">
      <div class="section-header">
        <div class="h2">Anomalies Detected</div>
        <span class="badge" id="anomalyCount">0</span>
      </div>
      <div id="anomalyList"></div>
    </div>
  </div>

  <!-- ════════ ACTIVITY TIMELINE ════════ -->
  <div class="section">
    <div class="section-inner">
      <div class="section-header">
        <div class="h2">Activity Timeline</div>
        <span class="badge" id="timelineCount">0 events</span>
      </div>
      <div id="activityTimeline"></div>
      <div id="timelineDetail" class="detail-panel"></div>
    </div>
  </div>

  <!-- ════════ ANALYTICS (existing dashboard features beneath) ════════ -->
  <div class="section">
    <div class="section-header">
      <div class="h2">Detailed Analytics</div>
      <span class="badge">drill-down</span>
    </div>

    <!-- KPI mini-grid -->
    <div class="grid-4" style="margin-bottom:16px;" id="kpiMiniGrid"></div>

    <div class="grid-2" style="margin-bottom:16px;">
      <div class="cell">
        <div class="h3" style="margin-bottom:8px;">Provider Distribution</div>
        <div id="providerBreakdown"></div>
      </div>
      <div class="cell">
        <div class="h3" style="margin-bottom:8px;">Model Utilization</div>
        <div id="modelUtilization"></div>
      </div>
    </div>

    <div class="grid-2">
      <div class="cell">
        <div class="h3" style="margin-bottom:8px;">Top Token-Consuming Sessions</div>
        <div id="topSessions"></div>
      </div>
      <div class="cell">
        <div class="h3" style="margin-bottom:8px;">System Resources (available)</div>
        <div id="systemResources"></div>
      </div>
    </div>
  </div>

  <!-- ════════ RAW TELEMETRY (collapsible) ════════ -->
  <div class="section">
    <div class="section-header">
      <div class="h2">Raw Telemetry <span style="font-weight:400;text-transform:none;letter-spacing:0;color:var(--text-dim);font-size:11px;">— click to expand</span></div>
      <span class="badge">source data</span>
    </div>
    <div id="rawTelemetry" style="display:none;"></div>
  </div>

  <div style="text-align:center;padding:24px 0 32px;color:var(--text-dim);font-size:11px;border-top:1px solid var(--border);">
    Hermes Command Center · Alfred Intelligence Layer · Data from <span class="mono">state.db</span> · Updated <span id="lastUpdated">—</span>
  </div>
</div>

<script>
// ── State ──
let intelligence = null;
let selectedInsight = null;
let selectedAttention = null;
let selectedDecision = null;
let selectedTimeline = null;
let selectedAnomaly = null;
let currentSort = { key: 'timestamp', dir: 'desc' };

// ── Format helpers ──
function fmtNum(n) {
  if (n == null || isNaN(n)) return '—';
  if (n >= 1e12) return (n / 1e12).toFixed(2) + 'T';
  if (n >= 1e9) return (n / 1e9).toFixed(2) + 'B';
  if (n >= 1e6) return (n / 1e6).toFixed(2) + 'M';
  if (n >= 1e3) return (n / 1e3).toFixed(1) + 'K';
  return n.toLocaleString();
}
function fmtInt(n) {
  if (n == null || isNaN(n)) return '—';
  return n.toLocaleString();
}
function fmtPct(n) {
  if (n == null || isNaN(n)) return '—';
  return n.toFixed(1) + '%';
}
function fmtDuration(s) {
  if (s == null || isNaN(s)) return '—';
  s = Number(s);
  if (s < 60) return s.toFixed(0) + 's';
  if (s < 3600) return (s/60).toFixed(1) + 'm';
  if (s < 86400) return (s/3600).toFixed(1) + 'h';
  return (s/86400).toFixed(1) + 'd';
}
function fmtDelta(pct) {
  if (pct == null || isNaN(pct)) return '—';
  if (pct > 0) return '↑ ' + pct.toFixed(1) + '%';
  if (pct < 0) return '↓ ' + Math.abs(pct).toFixed(1) + '%';
  return '→ stable';
}
function fmtTs(ts) {
  if (!ts) return '—';
  try {
    return new Date(Number(ts) * 1000).toLocaleString();
  } catch { return '—'; }
}
function timeAgo(ts) {
  if (!ts) return '—';
  const diff = Date.now() - Number(ts) * 1000;
  if (diff < 60000) return 'just now';
  if (diff < 3600000) return Math.floor(diff/60000) + 'm ago';
  if (diff < 86400000) return Math.floor(diff/3600000) + 'h ago';
  return Math.floor(diff/86400000) + 'd ago';
}

// ── API call ──
async function api(path) {
  const res = await fetch(path);
  if (!res.ok) throw new Error('API ' + path + ' ' + res.status);
  return res.json();
}

// ── Render system status grid ──
function renderStatusGrid(status) {
  const grid = document.getElementById('statusGrid');
  const items = [
    {
      label: 'System Status',
      value: status.overall_label,
      cls: status.overall_status === 'critical' ? 'critical' : status.overall_status === 'warning' ? 'warning' : 'healthy',
      sub: status.activity_label + ' activity · ' + fmtInt(status.total_calls) + ' API calls',
      dot: status.overall_status === 'critical' ? 'red' : status.overall_status === 'warning' ? 'orange' : 'green',
    },
    {
      label: 'Active Agents',
      value: fmtInt(status.active_agents),
      cls: status.active_agents === 0 ? '' : status.active_agents <= 3 ? 'healthy' : '',
      sub: status.total_sessions + ' total sessions',
      dot: status.active_agents === 0 ? 'dim' : status.active_agents <= 3 ? 'green' : 'dim',
    },
    {
      label: 'Token Consumption',
      value: fmtNum(status.total_input + status.total_output),
      cls: status.total_input > 100000000 ? 'warning' : '',
      sub: fmtNum(status.total_input) + ' input · ' + fmtNum(status.total_output) + ' output',
      dot: status.total_input > 100000000 ? 'orange' : 'dim',
    },
    {
      label: 'Efficiency',
      value: status.input_pct.toFixed(1) + '%',
      cls: status.input_pct > 90 ? 'warning' : '',
      sub: 'I/O ratio: ' + status.io_ratio.toFixed(1) + ':1 · Cache: ' + status.cache_pct.toFixed(1) + '%',
      dot: status.input_pct > 90 ? 'orange' : 'dim',
    },
  ];
  grid.innerHTML = items.map(item => `
    <div class="cell ${item.cls}">
      <div class="flex items-center gap-4 mb-4">
        <span class="status-dot ${item.dot}"></span>
        <span class="kpi-label">${item.label}</span>
      </div>
      <div class="kpi-value">${item.value}</div>
      <div class="kpi-sub">${item.sub}</div>
    </div>
  `).join('');
}

// ── Render Alfred Assessment ──
function renderAlfredAssessment(briefing, status) {
  const el = document.getElementById('alfredAssessment');
  el.innerHTML = `
    <div class="alfred-assessment-row">
      <span class="alfred-label-small"><span class="fact-tag fact">FACT</span>System</span>
      <span class="alfred-value fact">${status.overall_label} — ${status.activity_label} activity</span>
    </div>
    <div class="alfred-assessment-row">
      <span class="alfred-label-small"><span class="fact-tag fact">FACT</span>Usage</span>
      <span class="alfred-value fact">${fmtNum(status.total_input + status.total_output)} total tokens · ${fmtNum(status.total_input)} input / ${fmtNum(status.total_output)} output · ${fmtInt(status.total_calls)} API calls</span>
    </div>
    <div class="alfred-assessment-row">
      <span class="alfred-label-small"><span class="fact-tag analysis">ANALYSIS</span>Input Share</span>
      <span class="alfred-value analysis">${status.input_pct.toFixed(1)}% of all token volume is input — ${status.input_pct > 90 ? 'highly input-bound' : 'moderately input-bound'}</span>
    </div>
    <div class="alfred-assessment-row">
      <span class="alfred-label-small"><span class="fact-tag analysis">ANALYSIS</span>Cache</span>
      <span class="alfred-value analysis">${status.cache_pct.toFixed(1)}% cache hit rate — ${status.cache_pct > 60 ? 'performing well' : status.cache_pct > 30 ? 'moderate' : 'low'}</span>
    </div>
    <div class="alfred-assessment-row">
      <span class="alfred-label-small"><span class="fact-tag analysis">ANALYSIS</span>Provider</span>
      <span class="alfred-value analysis">${status.primary_provider} is primary (${status.primary_provider_pct.toFixed(1)}% of input)</span>
    </div>
    <div class="alfred-assessment-row">
      <span class="alfred-label-small"><span class="fact-tag interpretation">ALFRED</span>Assessment</span>
      <span class="alfred-value interpretation">${briefing.biggest_concern}</span>
    </div>
    <div class="alfred-assessment-row" style="margin-top:4px;">
      <span class="alfred-label-small"><span class="fact-tag recommendation">RECOMMEND</span>Action</span>
      <span class="alfred-value recommendation">${briefing.recommended_action}</span>
    </div>
  `;
}

// ── Render Alfred Insights ──
function renderAlfredInsights(insights) {
  const el = document.getElementById('alfredInsights');
  if (!insights || insights.length === 0) {
    el.innerHTML = '<div class="empty-state">No significant insights generated from current telemetry.</div>';
    return;
  }
  el.innerHTML = insights.map((ins, i) => `
    <div class="insight-card" data-insight="${i}" onclick="selectInsight(${i})">
      <div class="insight-card-header">
        <span class="insight-severity ${ins.severity}"></span>
        <span class="insight-observation">${ins.observation}</span>
        <span class="insight-category">${ins.category}</span>
      </div>
      <div class="insight-evidence">
        ${ins.evidence.map(e => '• ' + e).join('<br>')}
      </div>
      <div class="insight-interpretation">${ins.interpretation}</div>
      <div class="insight-impact">${ins.impact}</div>
      <div class="insight-decision"><strong>Decision:</strong> ${ins.decision}</div>
    </div>
  `).join('');
}

function selectInsight(idx) {
  selectedInsight = selectedInsight === idx ? null : idx;
  document.querySelectorAll('.insight-card').forEach((c, i) => {
    c.classList.toggle('selected', i === selectedInsight);
  });
  renderInsightDetail(idx);
}

function renderInsightDetail(idx) {
  const el = document.getElementById('insightDetail');
  if (idx === null || idx === undefined) {
    el.classList.remove('active');
    el.innerHTML = '';
    return;
  }
  const ins = intelligence.alfred_insights[idx];
  if (!ins) return;
  el.classList.add('active');
  el.innerHTML = `
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
      <span class="h3">Insight Detail — ${ins.category}</span>
      <span class="badge" style="color:${ins.severity === 'warning' ? 'var(--warning)' : ins.severity === 'healthy' ? 'var(--healthy)' : 'var(--info)'};">${ins.severity}</span>
    </div>
    <div class="detail-row">
      <span class="detail-label">Observation</span>
      <span class="detail-value">${ins.observation}</span>
    </div>
    <div class="detail-row">
      <span class="detail-label">Evidence</span>
      <span class="detail-value" style="font-size:11px;color:var(--text-muted);">${ins.evidence.join(' · ')}</span>
    </div>
    <div class="detail-row">
      <span class="detail-label">Interpretation</span>
      <span class="detail-value" style="font-style:italic;">${ins.interpretation}</span>
    </div>
    <div class="detail-row">
      <span class="detail-label">Impact</span>
      <span class="detail-value" style="color:var(--text-muted);">${ins.impact}</span>
    </div>
    <div class="detail-row" style="border-bottom:none;padding-bottom:0;">
      <span class="detail-label">Recommendation</span>
      <span class="detail-value" style="color:var(--accent);font-weight:500;">${ins.decision}</span>
    </div>
    <div class="detail-row" style="border-bottom:none;padding-top:6px;">
      <span class="detail-label">Drill-down</span>
      <span class="detail-value">
        ${ins.drilldown_path ? ins.drilldown_path.map(p => `<span style="cursor:pointer;color:var(--accent);text-decoration:underline;hover:text(var(--accent));display:inline-block;margin-right:6px;" onclick="drillTo('${p}')">${p}</span>`).join('') : 'None available'}
      </span>
    </div>
  `;
}

// ── Render What Changed ──
function renderWhatChanged(changes) {
  const el = document.getElementById('whatChanged');
  const badge = document.getElementById('changeBadge');
  const detail = document.getElementById('whatChangedDetail');

  if (!changes || changes.length === 0) {
    el.innerHTML = '<div class="empty-state">No significant changes detected since the last period.</div>';
    badge.textContent = '0 changes';
    return;
  }

  badge.textContent = changes.length + ' changes';

  const significant = changes.filter(c => c.significant);
  const display = significant.length > 0 ? significant : changes.slice(0, 8);

  el.innerHTML = display.map((c, i) => {
    let deltaStr = '';
    let deltaCls = '';
    if (c.delta_pct != null) {
      deltaStr = fmtDelta(c.delta_pct);
      deltaCls = c.delta_pct > 5 ? 'up' : c.delta_pct < -5 ? 'down' : 'stable';
    } else if (c.direction === 'new') {
      deltaStr = 'new';
      deltaCls = 'up';
    } else {
      deltaStr = fmtNum(c.last_7d);
      deltaCls = '';
    }

    const label = c.metric;
    let valStr = '';
    if (c.is_provider || c.is_model) {
      valStr = fmtNum(c.last_7d) + ' tokens';
    } else if (c.is_efficiency) {
      valStr = c.last_7d.toFixed(1) + '% → ' + c.prev_7d.toFixed(1) + '%';
    } else {
      valStr = fmtNum(c.last_7d) + ' vs ' + fmtNum(c.prev_7d);
    }

    return `
      <div class="change-row" onclick="showChangeDetail(${i})">
        <div class="change-metric">${label}</div>
        <div class="change-values">${valStr}</div>
        <div class="change-delta ${deltaCls}">${deltaStr}</div>
      </div>
    `;
  }).join('');

  // Clear detail
  detail.classList.remove('active');
  detail.innerHTML = '';
}

function showChangeDetail(idx) {
  const detail = document.getElementById('whatChangedDetail');
  const c = intelligence.what_changed[idx];
  if (!c) return;
  detail.classList.add('active');
  detail.innerHTML = `
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
      <span class="h3">Change Detail — ${c.metric}</span>
      <span class="badge" style="color:${c.direction === 'new' ? 'var(--healthy)' : c.direction === 'up' ? 'var(--warning)' : 'var(--healthy)'};">${c.direction}</span>
    </div>
    <div class="detail-row">
      <span class="detail-label">Current Period</span>
      <span class="detail-value">${fmtNum(c.last_7d)} ${c.is_efficiency ? '%' : 'tokens'}</span>
    </div>
    <div class="detail-row">
      <span class="detail-label">Previous Period</span>
      <span class="detail-value">${fmtNum(c.prev_7d)} ${c.is_efficiency ? '%' : 'tokens'}</span>
    </div>
    <div class="detail-row">
      <span class="detail-label">Change</span>
      <span class="detail-value" style="color:${c.delta_pct > 0 ? 'var(--warning)' : c.delta_pct < 0 ? 'var(--healthy)' : 'var(--text)'};">${c.delta_pct != null ? fmtDelta(c.delta_pct) : c.direction === 'new' ? 'New — no previous data' : '—'}</span>
    </div>
    <div class="detail-row" style="border-bottom:none;">
      <span class="detail-label">Significance</span>
      <span class="detail-value">${c.significant ? 'Statistically significant change' : 'Minor fluctuation'}</span>
    </div>
  `;
}

// ── Render Attention Required ──
function renderAttentionList(alertCategories) {
  const el = document.getElementById('attentionList');
  const counts = { critical: 0, warning: 0, optimization: 0, healthy: 0, information: 0 };

  const items = [];
  for (const [level, alerts] of Object.entries(alertCategories || {})) {
    counts[level] = alerts.length;
    for (const a of alerts) {
      items.push({ ...a, level });
    }
  }

  // Update count badges
  document.getElementById('critCount').textContent = counts.critical;
  document.getElementById('warnCount').textContent = counts.warning;
  document.getElementById('optCount').textContent = counts.optimization;
  document.getElementById('healthyCount').textContent = counts.healthy;
  document.getElementById('infoCount').textContent = counts.information;

  if (items.length === 0) {
    el.innerHTML = '<div class="empty-state">No alerts — system is operating normally.</div>';
    document.getElementById('attentionDetail').classList.remove('active');
    return;
  }

  const icons = {
    critical: '🔴',
    warning: '🟠',
    optimization: '🟡',
    healthy: '🟢',
    information: '🔵',
  };

  el.innerHTML = items.map((a, i) => `
    <div class="attention-item" data-level="${a.level}" data-idx="${i}" onclick="selectAttention(${i})">
      <div class="attention-icon ${a.level}">${icons[a.level] || '•'}</div>
      <div class="attention-content">
        <div class="attention-title">${a.title}</div>
        <div class="attention-desc">${a.description}</div>
        <div class="attention-meta">
          <span><span class="label">Evidence:</span> ${a.evidence}</span>
          ${a.recommendation ? `<span><span class="label">Action:</span> ${a.recommendation}</span>` : ''}
          ${a.severity ? `<span><span class="label">Severity:</span> ${a.severity}</span>` : ''}
        </div>
      </div>
    </div>
  `).join('');
}

function selectAttention(idx) {
  selectedAttention = selectedAttention === idx ? null : idx;
  document.querySelectorAll('.attention-item').forEach((c, i) => {
    c.classList.toggle('selected', i === selectedAttention);
  });
  renderAttentionDetail(idx);
}

function renderAttentionDetail(idx) {
  const el = document.getElementById('attentionDetail');
  if (idx === null || idx === undefined) {
    el.classList.remove('active');
    el.innerHTML = '';
    return;
  }
  const items = [];
  for (const [level, alerts] of Object.entries(intelligence.attention_required || {})) {
    for (const a of alerts) items.push({ ...a, level });
  }
  const a = items[idx];
  if (!a) return;
  el.classList.add('active');
  el.innerHTML = `
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
      <span class="h3">Alert Detail — ${a.title}</span>
      <span class="badge" style="color:${a.level === 'critical' ? 'var(--critical)' : a.level === 'warning' ? 'var(--warning)' : a.level === 'optimization' ? 'var(--optimization)' : a.level === 'healthy' ? 'var(--healthy)' : 'var(--info)'};">${a.level}</span>
    </div>
    <div class="detail-row">
      <span class="detail-label">Description</span>
      <span class="detail-value">${a.description}</span>
    </div>
    <div class="detail-row">
      <span class="detail-label">Evidence</span>
      <span class="detail-value" style="color:var(--text-muted);">${a.evidence}</span>
    </div>
    <div class="detail-row">
      <span class="detail-label">Likely Cause</span>
      <span class="detail-value">${a.likely_cause || '—'}</span>
    </div>
    <div class="detail-row">
      <span class="detail-label">Recommended Action</span>
      <span class="detail-value" style="color:var(--accent);">${a.recommendation || '—'}</span>
    </div>
    <div class="detail-row" style="border-bottom:none;">
      <span class="detail-label">Severity</span>
      <span class="detail-value">${a.severity || '—'}</span>
    </div>
    ${a.session_id ? `
    <div class="detail-row" style="border-bottom:none;">
      <span class="detail-label">Session</span>
      <span class="detail-value" style="color:var(--accent);cursor:pointer;text-decoration:underline;" onclick="drillToSession('${a.session_id}')">${a.session_id.slice(-30)}</span>
    </div>` : ''}
  `;
}

// ── Render Decision Queue ──
function renderDecisionQueue(decisions) {
  const el = document.getElementById('decisionQueue');
  const count = document.getElementById('decisionCount');

  if (!decisions || decisions.length === 0) {
    el.innerHTML = '<div class="empty-state">No decisions queued. System is operating normally.</div>';
    count.textContent = '0 decisions';
    return;
  }

  count.textContent = decisions.length + ' decisions';

  const icons = {
    critical: '🔴',
    warning: '🟠',
    optimization: '🟡',
    healthy: '🟢',
  };

  el.innerHTML = decisions.map((d, i) => `
    <div class="decision-item" data-idx="${i}" onclick="selectDecision(${i})">
      <div class="decision-priority">${icons[d.priority] || '•'}</div>
      <div class="decision-body">
        <div class="decision-title">${d.title}</div>
        <div class="decision-why">${d.why}</div>
        <div class="decision-action ${d.priority}">
          <div class="action-label">${d.priority.toUpperCase()}</div>
          ${d.recommended_action}
        </div>
        ${d.evidence ? `<div style="font-size:10px;color:var(--text-dim);margin-top:4px;">Evidence: ${Array.isArray(d.evidence) ? d.evidence.join(' · ') : d.evidence}</div>` : ''}
      </div>
    </div>
  `).join('');
}

function selectDecision(idx) {
  selectedDecision = selectedDecision === idx ? null : idx;
  document.querySelectorAll('.decision-item').forEach((c, i) => {
    c.classList.toggle('selected', i === selectedDecision);
  });
  renderDecisionDetail(idx);
}

function renderDecisionDetail(idx) {
  const el = document.getElementById('decisionDetail');
  if (idx === null || idx === undefined) {
    el.classList.remove('active');
    el.innerHTML = '';
    return;
  }
  const decisions = intelligence.decision_queue || [];
  const d = decisions[idx];
  if (!d) return;
  el.classList.add('active');
  el.innerHTML = `
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
      <span class="h3">Decision Detail</span>
      <span class="badge" style="color:${d.priority === 'critical' ? 'var(--critical)' : d.priority === 'warning' ? 'var(--warning)' : d.priority === 'optimization' ? 'var(--optimization)' : 'var(--healthy)'};">${d.priority}</span>
    </div>
    <div class="detail-row">
      <span class="detail-label">Issue</span>
      <span class="detail-value">${d.title}</span>
    </div>
    <div class="detail-row">
      <span class="detail-label">Why</span>
      <span class="detail-value" style="color:var(--text-muted);">${d.why}</span>
    </div>
    ${Array.isArray(d.evidence) && d.evidence.length ? `
    <div class="detail-row">
      <span class="detail-label">Evidence</span>
      <span class="detail-value" style="font-size:11px;color:var(--text-muted);">${d.evidence.join(' · ')}</span>
    </div>` : ''}
    <div class="detail-row" style="border-bottom:none;padding-bottom:0;">
      <span class="detail-label">Recommended Action</span>
      <span class="detail-value" style="color:var(--accent);font-weight:500;">${d.recommended_action}</span>
    </div>
  `;
}

// ── Render Daily Briefing ──
function renderDailyBriefing(briefing) {
  const el = document.getElementById('dailyBriefing');
  if (!briefing) {
    el.innerHTML = '<div class="empty-state">No briefing available.</div>';
    return;
  }

  const rows = [
    { label: 'System Status', value: briefing.system_status, color: briefing.system_status.includes('Critical') ? 'var(--critical)' : briefing.system_status.includes('Warning') ? 'var(--warning)' : 'var(--healthy)' },
    { label: 'Activity', value: briefing.activity },
    { label: 'Usage Trend', value: briefing.usage_trend, color: briefing.usage_trend.includes('↑') ? 'var(--warning)' : briefing.usage_trend.includes('↓') ? 'var(--healthy)' : 'var(--text-dim)' },
    { label: 'Efficiency', value: briefing.efficiency_trend, color: briefing.efficiency_trend.includes('↓') ? 'var(--warning)' : briefing.efficiency_trend.includes('↑') ? 'var(--healthy)' : 'var(--text-dim)' },
    { label: 'Error Status', value: briefing.error_status, color: briefing.error_status === 'Normal' ? 'var(--healthy)' : briefing.error_status === 'Low' ? 'var(--text-dim)' : 'var(--warning)' },
  ];

  el.innerHTML = `
    <div class="briefing-box">
      <div class="briefing-row">
        <span class="briefing-label">System</span>
        <span class="briefing-value" style="color:${rows[0].color};font-weight:600;">${rows[0].value}</span>
      </div>
      <div class="briefing-row">
        <span class="briefing-label">Activity Level</span>
        <span class="briefing-value">${rows[1].value}</span>
      </div>
      <div class="briefing-row">
        <span class="briefing-label">Usage Trend</span>
        <span class="briefing-value" style="color:${rows[2].color};">${rows[2].value}</span>
      </div>
      <div class="briefing-row">
        <span class="briefing-label">Efficiency Trend</span>
        <span class="briefing-value" style="color:${rows[3].color};">${rows[3].value}</span>
      </div>
      <div class="briefing-row">
        <span class="briefing-label">Error Status</span>
        <span class="briefing-value" style="color:${rows[4].color};">${rows[4].value}</span>
      </div>
    </div>
    <div class="briefing-box">
      <div class="briefing-row">
        <span class="briefing-label">Biggest Change</span>
        <span class="briefing-value">${briefing.biggest_change}</span>
      </div>
      <div class="briefing-row">
        <span class="briefing-label">Biggest Concern</span>
        <span class="briefing-value" style="color:var(--warning);">${briefing.biggest_concern}</span>
      </div>
      <div class="briefing-row">
        <span class="briefing-label">Biggest Opportunity</span>
        <span class="briefing-value" style="color:var(--healthy);">${briefing.biggest_opportunity}</span>
      </div>
      <div class="briefing-row" style="padding-bottom:0;border-bottom:none;">
        <span class="briefing-label">Recommended Action</span>
        <span class="briefing-value" style="color:var(--accent);font-weight:500;">${briefing.recommended_action}</span>
      </div>
    </div>
    <div class="briefing-box" style="border-color:var(--border-soft);padding:8px 12px;">
      <div style="display:flex;gap:16px;font-size:11px;color:var(--text-muted);">
        <span>Tokens: <strong style="color:var(--text);font-family:monospace;">${fmtNum(briefing.total_input + briefing.total_output)}</strong></span>
        <span>Input: <strong style="color:var(--warning);font-family:monospace;">${fmtNum(briefing.total_input)}</strong></span>
        <span>Output: <strong style="color:var(--healthy);font-family:monospace;">${fmtNum(briefing.total_output)}</strong></span>
        <span>API Calls: <strong style="color:var(--text);font-family:monospace;">${fmtInt(briefing.total_calls)}</strong></span>
        <span>Active Sessions: <strong style="color:var(--text);font-family:monospace;">${fmtInt(briefing.active_sessions)}</strong></span>
        <span>Critical: <strong style="color:var(--critical);font-family:monospace;">${briefing.critical_count}</strong></span>
        <span>Warnings: <strong style="color:var(--warning);font-family:monospace;">${briefing.warning_count}</strong></span>
      </div>
    </div>
  `;
}

// ── Render Anomalies ──
function renderAnomalies(anomalies) {
  const el = document.getElementById('anomalyList');
  const count = document.getElementById('anomalyCount');

  if (!anomalies || anomalies.length === 0) {
    el.innerHTML = '<div class="empty-state">No anomalies detected.</div>';
    count.textContent = '0';
    return;
  }

  count.textContent = anomalies.length;

  el.innerHTML = anomalies.map((a, i) => `
    <div class="timeline-item" data-idx="${i}" onclick="selectAnomaly(${i})">
      <div class="timeline-time">${a.time_str ? a.time_str.split(' ')[1] || a.time_str : '—'}</div>
      <div class="timeline-content">
        <div class="timeline-title" style="color:${a.severity === 'warning' ? 'var(--warning)' : 'var(--text)'};">${a.title}</div>
        <div class="timeline-desc">${a.description}</div>
        <div class="timeline-tags">
          <span class="timeline-tag">${a.type}</span>
          <span class="timeline-tag" style="color:${a.severity === 'warning' ? 'var(--warning)' : 'var(--text-dim)'};">${a.severity}</span>
          ${a.likely_cause ? `<span class="timeline-tag">${a.likely_cause}</span>` : ''}
        </div>
      </div>
    </div>
  `).join('');
}

function selectAnomaly(idx) {
  selectedAnomaly = selectedAnomaly === idx ? null : idx;
  document.querySelectorAll('.timeline-item[data-idx]').forEach((c, i) => {
    if (parseInt(c.dataset.idx) === idx) {
      c.style.background = 'var(--surface-2)';
    } else {
      c.style.background = '';
    }
  });
  renderAnomalyDetail(idx);
}

function renderAnomalyDetail(idx) {
  const el = document.getElementById('anomalyDetail');
  if (idx === null || idx === undefined) {
    el.classList.remove('active');
    el.innerHTML = '';
    return;
  }
  const anomalies = intelligence.anomalies || [];
  const a = anomalies[idx];
  if (!a) return;
  el.classList.add('active');
  el.innerHTML = `
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
      <span class="h3">Anomaly Detail — ${a.title}</span>
      <span class="badge" style="color:${a.severity === 'warning' ? 'var(--warning)' : 'var(--info)'};">${a.severity}</span>
    </div>
    <div class="detail-row">
      <span class="detail-label">Type</span>
      <span class="detail-value">${a.type}</span>
    </div>
    <div class="detail-row">
      <span class="detail-label">Description</span>
      <span class="detail-value">${a.description}</span>
    </div>
    <div class="detail-row">
      <span class="detail-label">Evidence</span>
      <span class="detail-value" style="color:var(--text-muted);">${a.evidence}</span>
    </div>
    <div class="detail-row">
      <span class="detail-label">Likely Cause</span>
      <span class="detail-value">${a.likely_cause || '—'}</span>
    </div>
    ${a.recommendation ? `
    <div class="detail-row" style="border-bottom:none;">
      <span class="detail-label">Recommendation</span>
      <span class="detail-value" style="color:var(--accent);">${a.recommendation}</span>
    </div>` : ''}
    ${a.session_id ? `
    <div class="detail-row" style="border-bottom:none;">
      <span class="detail-label">Session</span>
      <span class="detail-value" style="color:var(--accent);cursor:pointer;text-decoration:underline;" onclick="drillToSession('${a.session_id}')">${a.session_id.slice(-30)}</span>
    </div>` : ''}
  `;
}

// ── Render Activity Timeline ──
function renderActivityTimeline(events) {
  const el = document.getElementById('activityTimeline');
  const count = document.getElementById('timelineCount');

  if (!events || events.length === 0) {
    el.innerHTML = '<div class="empty-state">No activity recorded.</div>';
    count.textContent = '0 events';
    return;
  }

  // Group by time for compactness
  const timeGroups = {};
  for (const e of events) {
    const key = e.time_str || fmtTs(e.timestamp);
    if (!timeGroups[key]) timeGroups[key] = [];
    timeGroups[key].push(e);
  }

  const sortedTimes = Object.keys(timeGroups).sort((a, b) => {
    const ta = timeGroups[a][0].timestamp || 0;
    const tb = timeGroups[b][0].timestamp || 0;
    return Number(tb) - Number(ta);
  });

  let html = '';
  for (const time of sortedTimes.slice(0, 80)) {
    const evts = timeGroups[time];
    for (let i = 0; i < evts.length; i++) {
      const e = evts[i];
      const icon = getEventIcon(e.event_type);
      const tagColor = getEventTagColor(e.event_type);
      html += `
        <div class="timeline-item" data-tseidx="${time}-${i}" onclick="selectTimelineEvent('${time}-${i}')">
          <div class="timeline-time">${time}</div>
          <div class="timeline-content">
            <div class="timeline-title">${icon} ${e.title}</div>
            <div class="timeline-desc">${e.description}</div>
            <div class="timeline-tags">
              <span class="timeline-tag" style="border-color:${tagColor};color:${tagColor};">${e.event_type.replace(/_/g,' ')}</span>
              <span class="timeline-tag">${e.platform}</span>
              <span class="timeline-tag">${e.model ? e.model.split('/').pop().slice(0,20) : '—'}</span>
              <span class="timeline-tag">${fmtNum(e.input_tokens)} in</span>
              <span class="timeline-tag">${fmtNum(e.output_tokens)} out</span>
              <span class="timeline-tag">${e.api_calls} calls</span>
            </div>
          </div>
        </div>
      `;
    }
  }

  el.innerHTML = html;
  count.textContent = events.length + ' events';
}

function getEventIcon(type) {
  const icons = {
    heavy_session: '⚡',
    large_context: '📦',
    cache_heavy: '📡',
    reasoning_heavy: '🧠',
    tool_use: '🔧',
    session: '•',
  };
  return icons[type] || '•';
}

function getEventTagColor(type) {
  const colors = {
    heavy_session: 'var(--warning)',
    large_context: 'var(--accent)',
    cache_heavy: 'var(--info)',
    reasoning_heavy: 'var(--optimization)',
    tool_use: 'var(--healthy)',
    session: 'var(--text-dim)',
  };
  return colors[type] || 'var(--text-dim)';
}

function selectTimelineEvent(key) {
  selectedTimeline = selectedTimeline === key ? null : key;
  const items = document.querySelectorAll('.timeline-item[data-tseidx]');
  items.forEach(c => {
    c.style.background = c.dataset.tseidx === key ? 'var(--surface-2)' : '';
  });
  renderTimelineDetail(key);
}

function renderTimelineDetail(key) {
  const el = document.getElementById('timelineDetail');
  if (!key) {
    el.classList.remove('active');
    el.innerHTML = '';
    return;
  }
  const events = intelligence.activity_timeline || [];
  for (const e of events) {
    const k = (e.time_str || fmtTs(e.timestamp)) + '-' + events.indexOf(e);
    if (k === key) {
      el.classList.add('active');
      el.innerHTML = `
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
          <span class="h3">Event Detail — ${e.title}</span>
          <span class="badge" style="border-color:${getEventTagColor(e.event_type)};color:${getEventTagColor(e.event_type)};">${e.event_type.replace(/_/g,' ')}</span>
        </div>
        <div class="detail-row">
          <span class="detail-label">Session</span>
          <span class="detail-value">${e.title}</span>
        </div>
        <div class="detail-row">
          <span class="detail-label">Model</span>
          <span class="detail-value" style="color:var(--accent);">${e.model}</span>
        </div>
        <div class="detail-row">
          <span class="detail-label">Platform</span>
          <span class="detail-value">${e.platform}</span>
        </div>
        <div class="detail-row">
          <span class="detail-label">Input Tokens</span>
          <span class="detail-value" style="color:var(--warning);">${fmtNum(e.input_tokens)}</span>
        </div>
        <div class="detail-row">
          <span class="detail-label">Output Tokens</span>
          <span class="detail-value" style="color:var(--healthy);">${fmtNum(e.output_tokens)}</span>
        </div>
        <div class="detail-row">
          <span class="detail-label">API Calls</span>
          <span class="detail-value">${fmtInt(e.api_calls)}</span>
        </div>
        <div class="detail-row">
          <span class="detail-label">Cache Read</span>
          <span class="detail-value" style="color:var(--info);">${fmtNum(e.cache_read)} (${e.input_tokens > 0 ? (e.cache_read / e.input_tokens * 100).toFixed(1) + '%' : '0%'})</span>
        </div>
        <div class="detail-row">
          <span class="detail-label">Reasoning</span>
          <span class="detail-value" style="color:var(--optimization);">${fmtNum(e.reasoning)}</span>
        </div>
        <div class="detail-row">
          <span class="detail-label">Messages</span>
          <span class="detail-value">${fmtInt(e.messages)}</span>
        </div>
        <div class="detail-row">
          <span class="detail-label">Tool Calls</span>
          <span class="detail-value">${fmtInt(e.tool_calls)}</span>
        </div>
        ${e.title_text ? `
        <div class="detail-row" style="border-bottom:none;">
          <span class="detail-label">Title</span>
          <span class="detail-value" style="font-style:italic;">${e.title_text}</span>
        </div>` : ''}
        ${e.session_id ? `
        <div class="detail-row" style="border-bottom:none;">
          <span class="detail-label">Session ID</span>
          <span class="detail-value" style="color:var(--accent);cursor:pointer;text-decoration:underline;font-size:10px;" onclick="drillToSession('${e.session_id}')">${e.session_id}</span>
        </div>` : ''}
      `;
      return;
    }
  }
}

// ── Render KPIs mini-grid ──
function renderKPIsMini(raw) {
  const grid = document.getElementById('kpiMiniGrid');
  if (!raw) return;
  const cards = [
    { label: 'Total Input', value: fmtNum(raw.total_input), cls: 'warning', sub: raw.providers ? raw.providers[0]?.provider + ' primarily' : '' },
    { label: 'Total Output', value: fmtNum(raw.total_output), cls: 'healthy', sub: 'I/O ratio: ' + (raw.total_output > 0 ? (raw.total_input / raw.total_output).toFixed(1) + ':1' : '—') },
    { label: 'Cache Read', value: fmtNum(raw.total_cache_read), cls: '', sub: raw.total_input > 0 ? (raw.total_cache_read / raw.total_input * 100).toFixed(1) + '% of input' : '' },
    { label: 'Reasoning', value: fmtNum(raw.total_reasoning), cls: '', sub: 'Thinking tokens' },
    { label: 'API Calls', value: fmtInt(raw.total_calls), cls: '', sub: 'Across ' + fmtInt(raw.unique_sessions) + ' sessions' },
    { label: 'Active Sessions', value: fmtInt(raw.active_sessions), cls: '', sub: raw.total_sessions + ' total' },
    { label: 'Primary Provider', value: raw.providers?.[0]?.provider || '—', cls: '', sub: raw.providers?.[0] ? (raw.providers[0].input_tokens / (raw.total_input || 1) * 100).toFixed(1) + '% of input' : '' },
    { label: 'Errors', value: raw.error_indicators?.sessions_with_end_reason ? ((raw.error_indicators.error_sessions || 0) + ' / ' + raw.error_indicators.sessions_with_end_reason) : '—', cls: raw.error_indicators?.error_sessions > 10 ? 'warning' : '', sub: raw.compression_health?.fails ? (raw.compression_health.fails + ' compression fails') : '' },
  ];
  grid.innerHTML = cards.map(c => `
    <div class="cell ${c.cls}">
      <div class="kpi-label">${c.label}</div>
      <div class="kpi-value" style="font-size:18px;">${c.value}</div>
      <div class="kpi-sub">${c.sub}</div>
    </div>
  `).join('');
}

// ── Render Provider Breakdown ──
function renderProviderBreakdown(raw) {
  const el = document.getElementById('providerBreakdown');
  if (!raw || !raw.providers || raw.providers.length === 0) {
    el.innerHTML = '<div class="empty-state" style="padding:16px;">No provider data.</div>';
    return;
  }
  const total = raw.total_input || 1;
  el.innerHTML = raw.providers.map(p => {
    const pct = (p.input_tokens / total * 100);
    return `
      <div class="change-row" style="padding:4px 0;border-bottom:1px solid var(--grid-line);">
        <div class="change-metric" style="width:auto;font-size:12px;">${p.provider}</div>
        <div style="flex:1;font-size:11px;color:var(--text-muted);display:flex;gap:8px;align-items:center;">
          <div style="flex:1;height:4px;background:var(--surface-2);border-radius:2px;overflow:hidden;">
            <div style="width:${Math.min(100, pct)}%;height:100%;background:${pct > 50 ? 'var(--warning)' : pct > 10 ? 'var(--accent)' : 'var(--text-dim)'};border-radius:2px;"></div>
          </div>
          <span style="width:60px;text-align:right;font-family:monospace;">${pct.toFixed(1)}%</span>
        </div>
        <div style="width:80px;text-align:right;font-size:11px;font-family:monospace;color:var(--text-muted);">${fmtNum(p.input_tokens)}</div>
      </div>
    `;
  }).join('');
}

// ── Render Model Utilization ──
function renderModelUtilization(raw) {
  const el = document.getElementById('modelUtilization');
  if (!raw || !raw.models || raw.models.length === 0) {
    el.innerHTML = '<div class="empty-state" style="padding:16px;">No model data.</div>';
    return;
  }
  el.innerHTML = raw.models.slice(0, 6).map(m => {
    const pct = m.context_limit > 0 ? (m.input_tokens / m.context_limit * 100) : 0;
    const barW = Math.min(100, pct);
    const barColor = pct > 80 ? 'var(--warning)' : pct > 40 ? 'var(--accent)' : 'var(--text-dim)';
    return `
      <div style="display:flex;gap:8px;align-items:center;padding:4px 0;border-bottom:1px solid var(--grid-line);font-size:11px;">
        <code style="color:var(--accent);width:180px;flex-shrink:0;font-size:10px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${m.model.split('/').pop().slice(0,25)}</code>
        <div style="flex:1;height:4px;background:var(--surface-2);border-radius:2px;overflow:hidden;">
          <div style="width:${barW}%;height:100%;background:${barColor};border-radius:2px;"></div>
        </div>
        <span style="width:50px;text-align:right;font-family:monospace;color:var(--text-muted);">${m.context_limit > 0 ? pct.toFixed(0) + '%' : '—'}</span>
        <span style="width:80px;text-align:right;font-family:monospace;color:var(--text-dim);">${fmtNum(m.input_tokens)}</span>
      </div>
    `;
  }).join('');
}

// ── Render Top Sessions ──
function renderTopSessions(raw) {
  const el = document.getElementById('topSessions');
  if (!raw || !raw.top_sessions || raw.top_sessions.length === 0) {
    el.innerHTML = '<div class="empty-state" style="padding:16px;">No session data.</div>';
    return;
  }
  el.innerHTML = raw.top_sessions.map((s, i) => `
    <div class="change-row" style="padding:3px 0;border-bottom:1px solid var(--grid-line);cursor:pointer;" onclick="drillToSessionByIndex(${i})">
      <div style="width:20px;text-align:right;color:var(--text-dim);font-size:10px;flex-shrink:0;">#${i+1}</div>
      <div style="flex:1;min-width:0;">
        <div style="font-size:12px;color:var(--text);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${s.display_name || s.session_id.slice(-25)}</div>
        <div style="font-size:10px;color:var(--text-muted);">${s.platform} · ${s.model.split('/').pop().slice(0,25)}</div>
      </div>
      <div style="width:100px;text-align:right;font-family:monospace;color:var(--warning);font-size:11px;flex-shrink:0;">${fmtNum(s.input_tokens)}</div>
      <div style="width:80px;text-align:right;font-family:monospace;color:var(--text-muted);font-size:10px;flex-shrink:0;">${s.api_calls} calls</span>
    </div>
  `).join('');
}

// ── Render System Resources ──
function renderSystemResources(raw) {
  const el = document.getElementById('systemResources');
  // We'll populate this from system_metrics if available in intelligence
  const sys = intelligence?.system_status;
  if (!sys) {
    el.innerHTML = '<div class="empty-state" style="padding:16px;">System resource telemetry not yet integrated. See <span style="color:var(--accent);cursor:pointer;" onclick="toggleRaw()">raw telemetry</span> for gateway state.</div>';
    return;
  }

  const indicators = sys.status_indicators || [];
  const items = indicators.map(ind => {
    const icon = ind[1] === 'healthy' ? '🟢' : ind[1] === 'warning' ? '🟠' : ind[1] === 'critical' ? '🔴' : '🔵';
    const color = ind[1] === 'healthy' ? 'var(--healthy)' : ind[1] === 'warning' ? 'var(--warning)' : ind[1] === 'critical' ? 'var(--critical)' : 'var(--info)';
    return `
      <div class="change-row" style="padding:3px 0;border-bottom:1px solid var(--grid-line);">
        <span style="color:${color};font-weight:600;width:80px;flex-shrink:0;font-size:11px;">${icon} ${ind[0]}</span>
        <span style="flex:1;font-size:11px;color:var(--text-muted);">${ind[2]}</span>
      </div>
    `;
  }).join('');
  el.innerHTML = items || '<div class="empty-state" style="padding:16px;">No indicator data.</div>';
}

// ── Raw telemetry toggle ──
function toggleRaw() {
  const el = document.getElementById('rawTelemetry');
  if (el.style.display === 'block') {
    el.style.display = 'none';
    return;
  }
  el.style.display = 'block';
  if (intelligence) {
    renderRawTelemetry(intelligence.raw);
  }
}

function renderRawTelemetry(raw) {
  const el = document.getElementById('rawTelemetry');
  if (!raw) {
    el.innerHTML = '<div class="empty-state">No raw telemetry available.</div>';
    return;
  }
  const sections = [
    {
      title: 'Grand Totals',
      rows: [
        ['Total Input', fmtNum(raw.total_input)],
        ['Total Output', fmtNum(raw.total_output)],
        ['Combined', fmtNum(raw.total_input + raw.total_output)],
        ['Cache Read', fmtNum(raw.total_cache_read)],
        ['Reasoning', fmtNum(raw.total_reasoning)],
        ['API Calls', fmtInt(raw.total_calls)],
        ['Unique Sessions', fmtInt(raw.unique_sessions)],
        ['Total Sessions (DB)', fmtInt(raw.total_sessions)],
        ['Active Sessions', fmtInt(raw.active_sessions)],
      ]
    },
    {
      title: 'Error Indicators',
      rows: Object.entries(raw.error_indicators || {}).map(([k, v]) => [k, String(v)])
    },
    {
      title: 'Compression Health',
      rows: Object.entries(raw.compression_health || {}).map(([k, v]) => [k, typeof v === 'number' ? v.toFixed(1) : String(v)])
    },
  ];

  let html = '';
  for (const section of sections) {
    html += `<div style="margin-bottom:16px;"><div class="h3" style="margin-bottom:6px;">${section.title}</div><div style="display:grid;grid-template-columns:200px 1fr;gap:8px 16px;font-size:11px;">`;
    for (const [label, value] of section.rows) {
      html += `<div style="color:var(--text-muted);">${label}</div><div style="color:var(--text);font-family:monospace;text-align:right;">${value}</div>`;
    }
    html += `</div></div>`;
  }

  if (raw.providers && raw.providers.length) {
    html += `<div style="margin-bottom:16px;"><div class="h3" style="margin-bottom:6px;">Providers</div><div style="display:grid;grid-template-columns:120px 1fr 80px 60px;gap:8px 16px;font-size:11px;">`;
    const total = raw.total_input || 1;
    html += `<div style="color:var(--text-muted);">Provider</div><div style="color:var(--text-muted);">Input / Output</div><div style="color:var(--text-muted);text-align:right;">Share</div><div style="color:var(--text-muted);text-align:right;">Sessions</div>`;
    for (const p of raw.providers) {
      const pct = (p.input_tokens / total * 100);
      html += `<div style="color:var(--text);">${p.provider}</div><div style="font-family:monospace;">${fmtNum(p.input_tokens)} / ${fmtNum(p.output_tokens)}</div><div style="font-family:monospace;text-align:right;">${pct.toFixed(1)}%</div><div style="font-family:monospace;text-align:right;">${p.sessions || 0}</div>`;
    }
    html += `</div></div>`;
  }

  if (raw.models && raw.models.length) {
    html += `<div style="margin-bottom:16px;"><div class="h3" style="margin-bottom:6px;">Models</div><div style="display:grid;grid-template-columns:160px 1fr 80px 60px 60px;gap:8px 16px;font-size:11px;">`;
    const total = raw.total_input || 1;
    html += `<div style="color:var(--text-muted);">Model</div><div style="color:var(--text-muted);">Input / Output</div><div style="color:var(--text-muted);text-align:right;">Share</div><div style="color:var(--text-muted);text-align:right;">Cache</div><div style="color:var(--text-muted);text-align:right;">Limit</div>`;
    for (const m of raw.models) {
      const pct = (m.input_tokens / total * 100);
      html += `<div style="color:var(--accent);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${m.model}</div><div style="font-family:monospace;">${fmtNum(m.input_tokens)} / ${fmtNum(m.output_tokens)}</div><div style="font-family:monospace;text-align:right;">${pct.toFixed(1)}%</div><div style="font-family:monospace;text-align:right;">${fmtNum(m.cache_read)}</div><div style="font-family:monospace;text-align:right;">${m.context_limit ? fmtInt(m.context_limit) : '—'}</div>`;
    }
    html += `</div></div>`;
  }

  el.innerHTML = html;
}

// ── Drill-down: session ──
function drillToSession(sessionId) {
  if (!intelligence) return;
  const sessions = intelligence.raw?.top_sessions || [];
  for (const s of sessions) {
    if (s.session_id === sessionId) {
      showSessionDetail(s);
      return;
    }
  }
  // Try to find in activity timeline
  for (const e of intelligence.activity_timeline || []) {
    if (e.session_id === sessionId) {
      selectTimelineEvent((e.time_str || fmtTs(e.timestamp)) + '-' + (intelligence.activity_timeline || []).indexOf(e));
      return;
    }
  }
  alert('Session ' + sessionId.slice(-20) + ' not found in current data');
}

function drillToSessionByIndex(idx) {
  const sessions = intelligence?.raw?.top_sessions || [];
  if (sessions[idx]) showSessionDetail(sessions[idx]);
}

function showSessionDetail(s) {
  const el = document.getElementById('decisionDetail');
  el.classList.add('active');
  el.innerHTML = `
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
      <span class="h3">Session Detail — ${s.display_name || s.session_id.slice(-25)}</span>
      <span class="badge" style="border-color:var(--accent);color:var(--accent);">${s.platform}</span>
    </div>
    <div class="detail-row">
      <span class="detail-label">Session ID</span>
      <span class="detail-value" style="color:var(--accent);font-size:10px;">${s.session_id}</span>
    </div>
    <div class="detail-row">
      <span class="detail-label">Platform</span>
      <span class="detail-value">${s.platform}</span>
    </div>
    <div class="detail-row">
      <span class="detail-label">Model</span>
      <span class="detail-value" style="color:var(--accent);">${s.model}</span>
    </div>
    <div class="detail-row">
      <span class="detail-label">Input Tokens</span>
      <span class="detail-value" style="color:var(--warning);">${fmtNum(s.input_tokens)}</span>
    </div>
    <div class="detail-row">
      <span class="detail-label">Output Tokens</span>
      <span class="detail-value" style="color:var(--healthy);">${fmtNum(s.output_tokens)}</span>
    </div>
    <div class="detail-row">
      <span class="detail-label">Cache Read</span>
      <span class="detail-value" style="color:var(--info);">${fmtNum(s.cache_read)} (${s.input_tokens > 0 ? (s.cache_read / s.input_tokens * 100).toFixed(1) + '%' : '0%'})</span>
    </div>
    <div class="detail-row">
      <span class="detail-label">Reasoning</span>
      <span class="detail-value" style="color:var(--optimization);">${fmtNum(s.reasoning)}</span>
    </div>
    <div class="detail-row">
      <span class="detail-label">API Calls</span>
      <span class="detail-value">${fmtInt(s.api_calls)}</span>
    </div>
    <div class="detail-row">
      <span class="detail-label">Messages</span>
      <span class="detail-value">${fmtInt(s.messages)}</span>
    </div>
    <div class="detail-row">
      <span class="detail-label">Context Limit</span>
      <span class="detail-value">${s.context_limit ? fmtInt(s.context_limit) : '—'}</span>
    </div>
    ${s.title ? `
    <div class="detail-row" style="border-bottom:none;">
      <span class="detail-label">Title</span>
      <span class="detail-value" style="font-style:italic;">${s.title}</span>
    </div>` : ''}
  `;
}

// ── Drill-to section ──
function drillTo(section) {
  const targets = {
    'providers': () => { toggleRaw(); setTimeout(() => document.querySelector('#rawTelemetry')?.scrollIntoView({behavior:'smooth'}), 100); },
    'models': () => { toggleRaw(); setTimeout(() => document.querySelector('#rawTelemetry')?.scrollIntoView({behavior:'smooth'}), 100); },
    'sessions': () => { toggleRaw(); setTimeout(() => document.querySelector('#rawTelemetry')?.scrollIntoView({behavior:'smooth'}), 100); },
    'timeline': () => { document.querySelector('#activityTimeline')?.scrollIntoView({behavior:'smooth'}); },
  };
  if (targets[section]) targets[section]();
}

// ── Main refresh ──
async function refreshAll() {
  const btn = document.querySelector('button[onclick="refreshAll()"]');
  if (btn) { btn.textContent = '⟳ Refreshing…'; btn.disabled = true; }

  try {
    intelligence = await api('/api/intelligence');

    const now = new Date();
    document.getElementById('systemTime').textContent = now.toLocaleString();
    document.getElementById('lastUpdated').textContent = now.toLocaleTimeString();

    // System status
    renderStatusGrid(intelligence.system_status);

    // Alfred assessment
    renderAlfredAssessment(intelligence.daily_briefing, intelligence.system_status);

    // Alfred insights
    renderAlfredInsights(intelligence.alfred_insights);

    // What changed
    renderWhatChanged(intelligence.what_changed);

    // Attention required
    renderAttentionList(intelligence.attention_required);

    // Decision queue
    renderDecisionQueue(intelligence.decision_queue);

    // Daily briefing
    renderDailyBriefing(intelligence.daily_briefing);

    // Anomalies
    renderAnomalies(intelligence.anomalies);

    // Activity timeline
    renderActivityTimeline(intelligence.activity_timeline);

    // KPIs
    renderKPIsMini(intelligence.raw);

    // Provider/model breakdown
    renderProviderBreakdown(intelligence.raw);
    renderModelUtilization(intelligence.raw);
    renderTopSessions(intelligence.raw);
    renderSystemResources(intelligence);

    // Clear any open drill-down details
    document.querySelectorAll('.detail-panel').forEach(p => {
      if (p.id !== 'decisionDetail') p.classList.remove('active');
    });

  } catch (err) {
    console.error('Refresh failed:', err);
    alert('Failed to refresh intelligence data: ' + err.message);
  } finally {
    if (btn) { btn.textContent = '⟳ Refresh'; btn.disabled = false; }
  }
}

// ── Initial load ──
refreshAll();
setInterval(refreshAll, 30000);
</script>
</body>
</html>
"""


# ── Server runner ────────────────────────────────────────────────────

def run_server(port=DASHBOARD_PORT, open_browser=False):
    server = ThreadingHTTPServer(('127.0.0.1', port), CommandCenterHandler)
    CommandCenterHandler.server_port = port
    print(f"\n{'='*60}")
    print(f"  Hermes Command Center — Alfred Intelligence")
    print(f"{'='*60}")
    print(f"  URL:        http://127.0.0.1:{port}")
    print(f"  Data from:  {DB_PATH}")
    print(f"  Port:       {port}")
    print(f"  API:        /api/intelligence")
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
