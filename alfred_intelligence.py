#!/usr/bin/env python3
"""
Hermes Command Center — Alfred Intelligence Engine
Computes operational intelligence from raw Hermes telemetry.
"""

import json
import os
import sqlite3
import time
import datetime
from collections import defaultdict
from statistics import mean, stdev

HERMES_HOME = os.environ.get("HERMES_HOME", os.path.expanduser("~/.hermes"))
DB_PATH = os.path.join(HERMES_HOME, "state.db")
STATE_DIR = os.path.join(HERMES_HOME, "state")
GATEWAY_STATE = os.path.join(HERMES_HOME, "gateway_state.json")
PROCESSES_JSON = os.path.join(HERMES_HOME, "processes.json")
CRON_JOBS = os.path.join(HERMES_HOME, "cron/jobs.json")


# ── Database helpers (same as existing dashboard) ──────────────────

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


# ── Context limits (shared with dashboard) ─────────────────────────

CONTEXT_LIMITS = {
    "upstage/solar-pro4:free": 524288,
    "google/gemini-3.6-flash": 1048576,
    "stepfun/step-3.7-flash:free": 524288,
    "upstage/solar-pro4:free@https://inference-api.nousresearch.com/v1": 524288,
    "google/gemini-3.6-flash@https://inference-api.nousresearch.com/v1": 1048576,
}
KNOWN_LIMITS = {
    "upstage/solar-pro4:free": 524288,
    "google/gemini-3.6-flash": 1048576,
    "stepfun/step-3.7-flash:free": 524288,
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
    "google/gemma-4-26b-a4b-it:free": 131072,
    "deepseek-ai/deepseek-v4-flash-0731": 128000,
    "nvidia/nemotron-3-ultra-550b-a55b": 131072,
    "nvidia/nemotron-3-ultra-550b-a55b:free": 131072,
    "z-ai/glm-5.2": 128000,
    "nvidia/llama-3.3-nemotron-super-49b-v1": 128000,
    "meituan/longcat-2.0:free": 128000,
}


def get_context_limit(model):
    if not model or not isinstance(model, str):
        return 0
    if model in CONTEXT_LIMITS:
        return CONTEXT_LIMITS[model]
    if model in KNOWN_LIMITS:
        return KNOWN_LIMITS[model]
    clean = model.split("@")[0]
    if clean in KNOWN_LIMITS:
        return KNOWN_LIMITS[clean]
    if clean in CONTEXT_LIMITS:
        return CONTEXT_LIMITS[clean]
    return 0


# ── System metrics (from local machine) ────────────────────────────

def get_system_metrics():
    """Collect local system metrics where available."""
    metrics = {
        "cpu_percent": None,
        "memory_total_gb": None,
        "memory_used_gb": None,
        "memory_percent": None,
        "disk_info": [],
        "top_processes": [],
        "hermes_processes": [],
        "gateway_health": None,
        "active_agents": [],
        "cron_jobs": [],
        "python_processes": [],
    }

    # Try PowerShell for CPU/RAM/disk (Windows)
    try:
        import subprocess

        def run_ps1(code):
            ps1_path = os.path.join(HERMES_HOME, "scripts", "_cc_snap.ps1")
            os.makedirs(os.path.dirname(ps1_path), exist_ok=True)
            with open(ps1_path, "w") as f:
                f.write(code)
            try:
                r = subprocess.run(
                    ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", ps1_path],
                    capture_output=True, text=True, timeout=10
                )
                try:
                    os.unlink(ps1_path)
                except:
                    pass
                return r.stdout.strip()
            except:
                try:
                    os.unlink(ps1_path)
                except:
                    pass
                return ""

        # CPU
        cpu_out = run_ps1(
            '$c=Get-CimInstance Win32_Processor|Select-Object -First 1;'
            'Write-Output("{0}" -f $c.LoadPercentage)'
        )
        if cpu_out and cpu_out.replace('.','').replace('%','').isdigit():
            metrics["cpu_percent"] = float(cpu_out.replace('%', ''))

        # Memory
        mem_out = run_ps1(
            '$os=Get-CimInstance Win32_OperatingSystem;'
            '$t=[math]::Round($os.TotalVisibleMemorySize/1MB,1);'
            '$f=[math]::Round($os.FreePhysicalMemory/1MB,1);'
            '$u=[math]::Round($t-$f,1);'
            '$p=[math]::Round(($u/$t)*100,1);'
            'Write-Output("{0},{1},{2},{3}" -f $u,$t,$p,$f)'
        )
        if mem_out and ',' in mem_out:
            parts = mem_out.split(',')
            if len(parts) == 4:
                metrics["memory_used_gb"] = float(parts[0])
                metrics["memory_total_gb"] = float(parts[1])
                metrics["memory_percent"] = float(parts[2])
                metrics["memory_free_gb"] = float(parts[3])

        # Disk
        disk_out = run_ps1(
            'Get-PSDrive -PSProvider FileSystem|Where-Object{$_.Used-ne $null}|'
            'ForEach-Object{'
            '$n=$_.Name;'
            '$u=[math]::Round($_.Used/1GB,1);'
            '$f=[math]::Round($_.Free/1GB,1);'
            '$t=[math]::Round($u+$f,1);'
            '\"' + '$n' + '|' + '$u' + '|' + '$t' + '|' + '$f' + '\"'
            '}'
        )
        if disk_out:
            for line in disk_out.splitlines():
                line = line.strip().strip('"')
                if '|' in line:
                    parts = line.split('|')
                    if len(parts) == 4:
                        metrics["disk_info"].append({
                            "drive": parts[0],
                            "used_gb": float(parts[1]),
                            "total_gb": float(parts[2]),
                            "free_gb": float(parts[3]),
                        })

        # Top CPU processes
        top_out = run_ps1(
            'Get-Process|Sort-Object CPU -Descending|'
            'Select-Object -First 8|'
            'ForEach-Object{'
            '$n=$_.ProcessName;'
            '$c=[math]::Round($_.CPU/60,1);'
            '$m=[math]::Round($_.WS/1MB,0);'
            '\"' + '$n' + '|' + '$c' + '|' + '$m' + '\"'
            '}'
        )
        if top_out:
            for line in top_out.splitlines():
                line = line.strip().strip('"')
                if '|' in line:
                    parts = line.split('|')
                    if len(parts) == 3:
                        metrics["top_processes"].append({
                            "name": parts[0],
                            "cpu_minutes": float(parts[1]),
                            "ram_mb": int(parts[2]),
                        })

        # Python processes
        py_out = run_ps1(
            'Get-Process -Name python,python3,pythonw -ErrorAction SilentlyContinue|'
            'ForEach-Object{'
            '$n=$_.ProcessName;'
            '$ pid=$_.Id;'
            '$c=[math]::Round($_.CPU/60,1);'
            '$m=[math]::Round($_.WS/1MB,0);'
            '\"' + '$n' + '|' + '$pid' + '|' + '$c' + '|' + '$m' + '\"'
            '}'
        )
        if py_out:
            for line in py_out.splitlines():
                line = line.strip().strip('"')
                if '|' in line:
                    parts = line.split('|')
                    if len(parts) == 4:
                        metrics["python_processes"].append({
                            "name": parts[0],
                            "pid": int(parts[1]),
                            "cpu_minutes": float(parts[2]),
                            "ram_mb": int(parts[3]),
                        })

    except Exception:
        pass

    # Hermes processes from processes.json
    try:
        if os.path.exists(PROCESSES_JSON):
            data = json.loads(open(PROCESSES_JSON).read())
            arr = data if isinstance(data, list) else [data]
            now_s = time.time()
            for e in arr:
                if not isinstance(e, dict):
                    continue
                cmd = e.get("command") or ""
                label = cmd.split("/")[-1].split("\\")[-1].split(" ")[0]
                if not label or label in (".", ".."):
                    label = cmd.split()[-1] if cmd else "process"
                if len(label) > 30:
                    label = label[:30]
                started = e.get("started_at", 0)
                try:
                    started_f = float(started) if started else 0
                    uptime_s = max(0, int(now_s - started_f))
                except:
                    uptime_s = 0
                is_hermes = "hermes" in cmd.lower() or "gateway" in cmd.lower()
                metrics["hermes_processes"].append({
                    "label": label,
                    "pid": e.get("pid"),
                    "uptime_seconds": uptime_s,
                    "uptime_human": format_duration(uptime_s),
                    "command": cmd[:120],
                    "is_hermes": is_hermes,
                })
    except Exception:
        pass

    # Gateway health
    try:
        import urllib.request
        if os.path.exists(GATEWAY_STATE):
            gs = json.loads(open(GATEWAY_STATE).read())
            metrics["gateway_state"] = gs
        # Try health endpoint
        try:
            req = urllib.request.Request("http://127.0.0.1:8642/health")
            with urllib.request.urlopen(req, timeout=3) as resp:
                metrics["gateway_health"] = json.loads(resp.read())
        except:
            metrics["gateway_health"] = {"status": "unreachable"}
    except Exception:
        pass

    # Cron jobs
    try:
        if os.path.exists(CRON_JOBS):
            data = json.loads(open(CRON_JOBS).read())
            jobs = data.get("jobs", []) if isinstance(data, dict) else []
            metrics["cron_jobs"] = []
            for j in jobs:
                if not isinstance(j, dict):
                    continue
                metrics["cron_jobs"].append({
                    "name": j.get("name", "?"),
                    "state": j.get("state", "?"),
                    "schedule": j.get("schedule_display", j.get("schedule", {})),
                    "last_status": j.get("last_status", "?"),
                    "next_run": j.get("next_run_at", ""),
                })
    except Exception:
        pass

    return metrics


# ── Core telemetry queries ──────────────────────────────────────────

def get_telemetry_data():
    """Pull all raw telemetry needed for intelligence computation."""
    data = {}

    # Grand totals from session_model_usage
    smu = db_query_one("""
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
    """)
    data["smu"] = smu or {}

    # Sessions summary
    sess = db_query_one("""
        SELECT COUNT(*) as session_count,
               SUM(input_tokens) as sess_input,
               SUM(output_tokens) as sess_output,
               SUM(cache_read_tokens) as sess_cache_read,
               SUM(cache_write_tokens) as sess_cache_write,
               SUM(reasoning_tokens) as sess_reasoning,
               SUM(api_call_count) as sess_api_calls
        FROM sessions
    """)
    data["sessions_summary"] = sess or {}

    # Model aggregation
    models = db_query("""
        SELECT model, billing_provider,
               SUM(input_tokens) as total_input,
               SUM(output_tokens) as total_output,
               SUM(cache_read_tokens) as total_cache_read,
               SUM(reasoning_tokens) as total_reasoning,
               SUM(api_call_count) as total_calls,
               COUNT(DISTINCT session_id) as sessions
        FROM session_model_usage
        GROUP BY model, billing_provider
        ORDER BY total_input DESC
    """)
    data["models"] = models

    # Provider aggregation
    providers = db_query("""
        SELECT billing_provider,
               SUM(input_tokens) as total_input,
               SUM(output_tokens) as total_output,
               SUM(cache_read_tokens) as total_cache_read,
               SUM(api_call_count) as total_calls,
               COUNT(DISTINCT session_id) as sessions
        FROM session_model_usage
        GROUP BY billing_provider
        ORDER BY total_input DESC
    """)
    data["providers"] = providers

    # Active sessions
    active = db_query("""
        SELECT id, session_key, display_name, model, started_at,
               input_tokens, output_tokens, cache_read_tokens,
               reasoning_tokens, message_count, tool_call_count,
               api_call_count, last_activity_description, title,
               billing_provider, billing_mode
        FROM sessions
        WHERE ended_at IS NULL OR ended_at = 0
        ORDER BY started_at DESC
    """)
    data["active_sessions"] = active

    # Timeline (all time, hourly)
    timeline = db_query("""
        SELECT 
            CAST(strftime('%s', first_seen, 'unixepoch') AS INTEGER) as hour_ts,
            strftime('%Y-%m-%d %H:00', first_seen, 'unixepoch') as hour_label,
            SUM(input_tokens) as input,
            SUM(output_tokens) as output,
            SUM(cache_read_tokens) as cache_read,
            SUM(reasoning_tokens) as reasoning,
            COUNT(DISTINCT session_id) as sessions
        FROM session_model_usage
        GROUP BY hour_ts
        ORDER BY hour_ts ASC
    """)
    data["timeline"] = timeline

    # Last 7 days vs previous 7 days
    # If prev7 is empty (data spans < 14 days), split last 7 days in half
    now_ts = time.time()
    week_ago = now_ts - 7 * 86400
    two_weeks_ago = now_ts - 14 * 86400

    last7 = db_query_one("""
        SELECT 
            SUM(input_tokens) as input,
            SUM(output_tokens) as output,
            SUM(cache_read_tokens) as cache_read,
            SUM(reasoning_tokens) as reasoning,
            SUM(api_call_count) as calls,
            COUNT(DISTINCT session_id) as sessions
        FROM session_model_usage
        WHERE first_seen > ?
    """, (week_ago,))
    data["last_7_days"] = last7 or {}

    prev7 = db_query_one("""
        SELECT 
            SUM(input_tokens) as input,
            SUM(output_tokens) as output,
            SUM(cache_read_tokens) as cache_read,
            SUM(reasoning_tokens) as reasoning,
            SUM(api_call_count) as calls,
            COUNT(DISTINCT session_id) as sessions
        FROM session_model_usage
        WHERE first_seen > ? AND first_seen <= ?
    """, (two_weeks_ago, week_ago,))
    data["prev_7_days"] = prev7 or {}

    # Fallback: if prev7 is empty, use first half of available data as baseline
    if not prev7 or safe_num(prev7.get("calls")) == 0:
        data_start = db_query_one("SELECT MIN(first_seen) as mn, MAX(first_seen) as mx FROM session_model_usage")
        data_min = data_start.get("mn") if data_start else 0
        data_max = data_start.get("mx") if data_start else 0
        if data_min and data_max and data_min < data_max:
            midpoint = data_min + (data_max - data_min) / 2
            prev7_fallback = db_query_one("""
                SELECT 
                    SUM(input_tokens) as input,
                    SUM(output_tokens) as output,
                    SUM(cache_read_tokens) as cache_read,
                    SUM(reasoning_tokens) as reasoning,
                    SUM(api_call_count) as calls,
                    COUNT(DISTINCT session_id) as sessions
                FROM session_model_usage
                WHERE first_seen >= ? AND first_seen <= ?
            """, (data_min, midpoint))
            if prev7_fallback and safe_num(prev7_fallback.get("calls")) > 0:
                data["prev_7_days"] = prev7_fallback
                data["prev_7_days_fallback"] = True
                data["prev_7_days_fallback_midpoint"] = midpoint
            else:
                data["prev_7_days_fallback"] = False

    # Channel/platform breakdown
    channels = db_query("""
        SELECT 
            CASE 
                WHEN s.session_key LIKE '%telegram:dm:%' THEN 'Telegram DM'
                WHEN s.session_key LIKE '%telegram:group:%' THEN 'Telegram Group'
                WHEN s.session_key LIKE '%discord:dm:%' THEN 'Discord DM'
                WHEN s.session_key LIKE '%batcave%' OR s.session_key LIKE '%captain%' THEN "CaptainL's Batcave"
                WHEN s.session_key LIKE '%agent:main%' THEN 'Gateway'
                ELSE 'CLI'
            END as platform_group,
            SUM(su.input_tokens) as total_input,
            SUM(su.output_tokens) as total_output,
            SUM(su.cache_read_tokens) as total_cache_read,
            COUNT(DISTINCT su.session_id) as sessions,
            COUNT(*) as usage_rows
        FROM session_model_usage su
        JOIN sessions s ON su.session_id = s.id
        GROUP BY platform_group
        ORDER BY total_input DESC
    """)
    data["platform_groups"] = channels

    # Session detail with model info
    session_detail = db_query("""
        SELECT 
            su.session_id,
            su.model,
            su.billing_provider,
            su.billing_mode,
            su.input_tokens,
            su.output_tokens,
            su.cache_read_tokens,
            su.cache_write_tokens,
            su.reasoning_tokens,
            su.api_call_count,
            su.first_seen,
            su.last_seen,
            s.display_name,
            s.session_key,
            s.started_at,
            s.ended_at,
            s.message_count,
            s.tool_call_count,
            s.title,
            s.last_activity_description,
            s.model_config,
            s.end_reason,
            s.billing_provider as sess_provider,
            s.billing_mode as sess_mode
        FROM session_model_usage su
        LEFT JOIN sessions s ON su.session_id = s.id
        ORDER BY su.first_seen ASC
    """)
    for r in session_detail:
        r["context_limit"] = get_context_limit(r["model"])
        r["total_tokens"] = (r["input_tokens"] or 0) + (r["output_tokens"] or 0)
        r["input_share_pct"] = 0  # filled later
        start = r.get("started_at") or 0
        end = r.get("last_seen") or time.time()
        r["duration_seconds"] = max(0, end - start)
        r["first_seen_human"] = fmt_ts(r["first_seen"])
        r["last_seen_human"] = fmt_ts(r["last_seen"])
        if not r.get("display_name") and r.get("session_key"):
            r["display_name"] = infer_display(r["session_key"])
        r["platform"] = infer_platform(r.get("session_key", ""))
    data["session_detail"] = session_detail

    # Error indicators from sessions table
    errors = db_query_one("""
        SELECT 
            COUNT(*) as sessions_with_end_reason,
            SUM(CASE WHEN end_reason LIKE '%error%' OR end_reason LIKE '%failure%' THEN 1 ELSE 0 END) as error_sessions,
            SUM(CASE WHEN end_reason LIKE '%fallback%' THEN 1 ELSE 0 END) as fallback_sessions,
            SUM(CASE WHEN compression_failure_error IS NOT NULL AND compression_failure_error != '' THEN 1 ELSE 0 END) as compression_failures,
            SUM(CASE WHEN handoff_error IS NOT NULL AND handoff_error != '' THEN 1 ELSE 0 END) as handoff_errors
        FROM sessions
    """)
    data["error_indicators"] = errors or {}

    # Compression/sticky failure indicators
    compression = db_query_one("""
        SELECT 
            SUM(CASE WHEN compression_failure_error IS NOT NULL AND compression_failure_error != '' THEN 1 ELSE 0 END) as fails,
            SUM(compression_fallback_streak) as total_streaks,
            AVG(compression_fallback_streak) as avg_streak,
            MAX(compression_fallback_streak) as max_streak
        FROM sessions
        WHERE compression_failure_error IS NOT NULL
    """)
    data["compression_health"] = compression or {}

    # Recent activity (last 24 hours by hour)
    recent_timeline = db_query("""
        SELECT 
            strftime('%Y-%m-%d %H:00', first_seen, 'unixepoch') as hour,
            SUM(input_tokens) as input,
            SUM(output_tokens) as output,
            SUM(cache_read_tokens) as cache_read,
            SUM(api_call_count) as calls,
            COUNT(DISTINCT session_id) as sessions
        FROM session_model_usage
        WHERE first_seen > ?
        GROUP BY hour
        ORDER BY hour DESC
        LIMIT 24
    """, (now_ts - 86400,))
    data["recent_24h"] = list(reversed(recent_timeline))

    # Top token-consuming sessions
    top_sessions = db_query("""
        SELECT 
            su.session_id,
            su.model,
            su.input_tokens,
            su.output_tokens,
            su.cache_read_tokens,
            su.reasoning_tokens,
            su.api_call_count,
            su.first_seen,
            su.last_seen,
            s.display_name,
            s.session_key,
            s.started_at,
            s.ended_at,
            s.message_count,
            s.last_activity_description,
            s.title
        FROM session_model_usage su
        JOIN sessions s ON su.session_id = s.id
        ORDER BY su.input_tokens DESC
        LIMIT 10
    """)
    for r in top_sessions:
        r["context_limit"] = get_context_limit(r["model"])
        r["started_at_human"] = fmt_ts(r["started_at"])
        r["last_seen_human"] = fmt_ts(r["last_seen"])
        if not r.get("display_name") and r.get("session_key"):
            r["display_name"] = infer_display(r["session_key"])
        r["platform"] = infer_platform(r.get("session_key", ""))
    data["top_token_sessions"] = top_sessions

    return data


# ── Helpers ──────────────────────────────────────────────────────────

def fmt_ts(ts):
    if not ts:
        return "—"
    try:
        return datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
    except:
        return "—"


def format_duration(seconds):
    if seconds is None:
        return "—"
    if seconds < 60:
        return f"{seconds:.0f}s"
    if seconds < 3600:
        return f"{seconds/60:.1f}m"
    if seconds < 86400:
        return f"{seconds/3600:.1f}h"
    return f"{seconds/86400:.1f}d"


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
        return "CaptainL's Batcave"
    if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
        return f"Channel {parts[0][:15]}"
    return session_key[:40]


def safe_num(n, default=0):
    if n is None:
        return default
    try:
        return float(n)
    except:
        return default


def pct_change(new, old):
    if old is None or old == 0:
        return None
    return ((new - old) / old) * 100


# ── Intelligence Computation ────────────────────────────────────────

def compute_system_status(tdata, sys_metrics):
    """Compute overall system status and executive summary."""
    smu = tdata.get("smu", {})
    sess = tdata.get("sessions_summary", {})
    errors = tdata.get("error_indicators", {})
    active = tdata.get("active_sessions", [])
    providers = tdata.get("providers", [])
    compression = tdata.get("compression_health", {})

    total_input = safe_num(smu.get("total_input"))
    total_output = safe_num(smu.get("total_output"))
    total_calls = safe_num(smu.get("total_calls"))
    cache_read = safe_num(smu.get("total_cache_read"))
    error_count = safe_num(errors.get("error_sessions"))
    total_sessions_with_end = safe_num(errors.get("sessions_with_end_reason"))
    compression_fails = safe_num(compression.get("fails"))

    # Session health
    active_count = len(active)
    total_sessions = safe_num(sess.get("session_count"))

    # Error rate
    error_rate = (error_count / total_sessions_with_end * 100) if total_sessions_with_end > 0 else 0

    # Compression health
    has_compression_issues = compression_fails > 5

    # Provider distribution
    provider_input = {}
    for p in providers:
        prov = p.get("billing_provider") or "unknown"
        provider_input[prov] = safe_num(p.get("total_input"))

    primary_provider = max(provider_input, key=provider_input.get) if provider_input else "unknown"
    primary_pct = (provider_input.get(primary_provider, 0) / total_input * 100) if total_input > 0 else 0

    # Input/output ratio
    io_ratio = total_input / total_output if total_output > 0 else float('inf')
    input_pct = total_input / (total_input + total_output) * 100 if (total_input + total_output) > 0 else 100

    # Cache efficiency
    cache_pct = (cache_read / total_input * 100) if total_input > 0 else 0

    # API call volume
    calls_per_session = total_calls / safe_num(smu.get("unique_sessions")) if safe_num(smu.get("unique_sessions")) > 0 else 0

    # Determine status
    status_indicators = []

    # API health
    gw_health = sys_metrics.get("gateway_health", {})
    if gw_health.get("status") == "ok":
        status_indicators.append(("api", "healthy", "API server responding normally"))
    elif gw_health.get("status") == "unreachable":
        status_indicators.append(("api", "critical", "API server unreachable"))
    else:
        status_indicators.append(("api", "warning", "API server status unknown"))

    # Agent health
    if active_count == 0:
        status_indicators.append(("agents", "info", "No active agents"))
    elif active_count <= 3:
        status_indicators.append(("agents", "healthy", f"{active_count} active agent(s) — normal"))
    else:
        status_indicators.append(("agents", "info", f"{active_count} active agents"))

    # Error health
    if error_rate > 10:
        status_indicators.append(("errors", "critical", f"Error rate {error_rate:.1f}% — significant"))
    elif error_rate > 3:
        status_indicators.append(("errors", "warning", f"Error rate {error_rate:.1f}% — elevated"))
    elif error_count > 0:
        status_indicators.append(("errors", "info", f"{error_count} session(s) with errors"))
    else:
        status_indicators.append(("errors", "healthy", "No session errors recorded"))

    # Compression health
    if has_compression_issues:
        status_indicators.append(("compression", "warning", f"{compression_fails} compression failures recorded"))
    else:
        status_indicators.append(("compression", "healthy", "Compression functioning normally"))

    # Token efficiency
    if input_pct > 95:
        status_indicators.append(("efficiency", "warning", f"Input is {input_pct:.1f}% of token volume — highly input-bound"))
    elif input_pct > 85:
        status_indicators.append(("efficiency", "info", f"Input is {input_pct:.1f}% of token volume"))
    else:
        status_indicators.append(("efficiency", "healthy", f"Balanced input/output ratio"))

    # Overall status determination
    has_critical = any(s[1] == "critical" for s in status_indicators)
    has_warning = any(s[1] == "warning" for s in status_indicators)

    if has_critical:
        overall = "critical"
        overall_label = "🔴 Critical"
    elif has_warning:
        overall = "warning"
        overall_label = "🟠 Warning"
    else:
        overall = "healthy"
        overall_label = "🟢 Operational"

    # Activity level
    if total_calls == 0:
        activity_level = "none"
        activity_label = "No activity"
    elif total_calls < 100:
        activity_level = "low"
        activity_label = "Low"
    elif total_calls < 1000:
        activity_level = "moderate"
        activity_label = "Moderate"
    elif total_calls < 5000:
        activity_level = "high"
        activity_label = "High"
    else:
        activity_level = "very_high"
        activity_label = "Very High"

    return {
        "overall_status": overall,
        "overall_label": overall_label,
        "status_indicators": status_indicators,
        "active_agents": active_count,
        "total_sessions": total_sessions,
        "activity_level": activity_level,
        "activity_label": activity_label,
        "token_consumption_level": "elevated" if total_input > 100_000_000 else "normal",
        "provider_health": "normal" if not has_critical else "degraded",
        "api_errors": "low" if error_rate < 3 else "elevated",
        "efficiency_needs_attention": input_pct > 85,
        "io_ratio": round(io_ratio, 2),
        "input_pct": round(input_pct, 1),
        "cache_pct": round(cache_pct, 1),
        "calls_per_session": round(calls_per_session, 1),
        "primary_provider": primary_provider,
        "primary_provider_pct": round(primary_pct, 1),
        "total_input": total_input,
        "total_output": total_output,
        "total_calls": total_calls,
    }


def compute_what_changed(tdata):
    """Compare current state with historical baselines."""
    last7 = tdata.get("last_7_days", {})
    prev7 = tdata.get("prev_7_days", {})

    changes = []

    # API calls
    l7_calls = safe_num(last7.get("calls"))
    p7_calls = safe_num(prev7.get("calls"))
    delta_calls = pct_change(l7_calls, p7_calls)
    if delta_calls is not None:
        changes.append({
            "metric": "API Calls",
            "last_7d": l7_calls,
            "prev_7d": p7_calls,
            "delta_pct": round(delta_calls, 1),
            "direction": "up" if delta_calls > 0 else "down",
            "significant": abs(delta_calls) > 15,
        })

    # Input tokens
    l7_in = safe_num(last7.get("input"))
    p7_in = safe_num(prev7.get("input"))
    delta_in = pct_change(l7_in, p7_in)
    if delta_in is not None:
        changes.append({
            "metric": "Input Tokens",
            "last_7d": l7_in,
            "prev_7d": p7_in,
            "delta_pct": round(delta_in, 1),
            "direction": "up" if delta_in > 0 else "down",
            "significant": abs(delta_in) > 15,
        })

    # Output tokens
    l7_out = safe_num(last7.get("output"))
    p7_out = safe_num(prev7.get("output"))
    delta_out = pct_change(l7_out, p7_out)
    if delta_out is not None:
        changes.append({
            "metric": "Output Tokens",
            "last_7d": l7_out,
            "prev_7d": p7_out,
            "delta_pct": round(delta_out, 1),
            "direction": "up" if delta_out > 0 else "down",
            "significant": abs(delta_out) > 15,
        })

    # Cache read
    l7_cache = safe_num(last7.get("cache_read"))
    p7_cache = safe_num(prev7.get("cache_read"))
    delta_cache = pct_change(l7_cache, p7_cache)
    if delta_cache is not None and p7_cache > 0:
        # Cache efficiency: cache_read / input
        l7_eff = (l7_cache / l7_in * 100) if l7_in > 0 else 0
        p7_eff = (p7_cache / p7_in * 100) if p7_in > 0 else 0
        delta_eff = l7_eff - p7_eff
        changes.append({
            "metric": "Cache Efficiency",
            "last_7d": round(l7_eff, 1),
            "prev_7d": round(p7_eff, 1),
            "delta_pct": round(delta_eff, 1),
            "direction": "up" if delta_eff > 0 else "down",
            "significant": abs(delta_eff) > 5,
            "is_efficiency": True,
        })

    # Provider shifts — compare recent half vs early half if prev7 empty
    last7_providers = {}
    prev7_providers = {}

    # Get provider breakdown for each period
    now_ts = time.time()
    week_ago = now_ts - 7 * 86400
    two_weeks_ago = now_ts - 14 * 86400

    lp = db_query("""
        SELECT billing_provider, SUM(input_tokens) as input
        FROM session_model_usage
        WHERE first_seen > ?
        GROUP BY billing_provider
    """, (week_ago,))
    for r in lp:
        last7_providers[r["billing_provider"] or "unknown"] = safe_num(r["input"])

    pp = db_query("""
        SELECT billing_provider, SUM(input_tokens) as input
        FROM session_model_usage
        WHERE first_seen > ? AND first_seen <= ?
        GROUP BY billing_provider
    """, (two_weeks_ago, week_ago))
    for r in pp:
        prev7_providers[r["billing_provider"] or "unknown"] = safe_num(r["input"])

    # Fallback: if prev7 empty, split data range into early/late halves
    if not pp or (pp and safe_num(pp[0].get("input")) == 0):
        data_start = db_query_one("SELECT MIN(first_seen) as mn, MAX(first_seen) as mx FROM session_model_usage")
        data_min = data_start.get("mn") if data_start else 0
        data_max = data_start.get("mx") if data_start else 0
        if data_min and data_max and data_min < data_max:
            midpoint = data_min + (data_max - data_min) / 2
            pp_fb = db_query("""
                SELECT billing_provider, SUM(input_tokens) as input
                FROM session_model_usage
                WHERE first_seen >= ? AND first_seen <= ?
                GROUP BY billing_provider
            """, (data_min, midpoint))
            prev7_providers = {}
            for r in pp_fb:
                prev7_providers[r["billing_provider"] or "unknown"] = safe_num(r["input"])

    # Find significant provider shifts
    all_providers = set(last7_providers.keys()) | set(prev7_providers.keys())
    for prov in sorted(all_providers):
        l7p = last7_providers.get(prov, 0)
        p7p = prev7_providers.get(prov, 0)
        if p7p == 0 and l7p > 0:
            changes.append({
                "metric": f"Provider: {prov}",
                "last_7d": l7p,
                "prev_7d": p7p,
                "delta_pct": None,
                "direction": "new",
                "significant": True,
                "is_provider": True,
            })
        elif p7p > 0:
            delta = pct_change(l7p, p7p)
            if delta is not None and abs(delta) > 20:
                changes.append({
                    "metric": f"Provider: {prov}",
                    "last_7d": l7p,
                    "prev_7d": p7p,
                    "delta_pct": round(delta, 1),
                    "direction": "up" if delta > 0 else "down",
                    "significant": True,
                    "is_provider": True,
                })

    # Model shifts — compare recent half vs early half if prev7 empty
    last7_models = {}
    prev7_models = {}
    lm = db_query("""
        SELECT model, SUM(input_tokens) as input
        FROM session_model_usage
        WHERE first_seen > ?
        GROUP BY model
    """, (week_ago,))
    for r in lm:
        last7_models[r["model"]] = safe_num(r["input"])

    pm = db_query("""
        SELECT model, SUM(input_tokens) as input
        FROM session_model_usage
        WHERE first_seen > ? AND first_seen <= ?
        GROUP BY model
    """, (two_weeks_ago, week_ago,))
    for r in pm:
        prev7_models[r["model"]] = safe_num(r["input"])

    # Fallback: if prev7 empty, split data range into early/late halves
    if not pm or (pm and safe_num(pm[0].get("input")) == 0):
        data_start = db_query_one("SELECT MIN(first_seen) as mn, MAX(first_seen) as mx FROM session_model_usage")
        data_min = data_start.get("mn") if data_start else 0
        data_max = data_start.get("mx") if data_start else 0
        if data_min and data_max and data_min < data_max:
            midpoint = data_min + (data_max - data_min) / 2
            pm_fb = db_query("""
                SELECT model, SUM(input_tokens) as input
                FROM session_model_usage
                WHERE first_seen >= ? AND first_seen <= ?
                GROUP BY model
            """, (data_min, midpoint))
            prev7_models = {}
            for r in pm_fb:
                prev7_models[r["model"]] = safe_num(r["input"])

    all_models = set(last7_models.keys()) | set(prev7_models.keys())
    for model in sorted(all_models):
        l7m = last7_models.get(model, 0)
        p7m = prev7_models.get(model, 0)
        if p7m == 0 and l7m > 1_000_000:
            changes.append({
                "metric": f"Model: {model[:40]}",
                "last_7d": l7m,
                "prev_7d": p7m,
                "delta_pct": None,
                "direction": "new",
                "significant": True,
                "is_model": True,
            })
        elif p7m > 0:
            delta = pct_change(l7m, p7m)
            if delta is not None and abs(delta) > 30:
                changes.append({
                    "metric": f"Model: {model[:40]}",
                    "last_7d": l7m,
                    "prev_7d": p7m,
                    "delta_pct": round(delta, 1),
                    "direction": "up" if delta > 0 else "down",
                    "significant": True,
                    "is_model": True,
                })

    return changes


def compute_attention_required(tdata, sys_metrics):
    """Generate prioritized alerts: Critical, Warning, Optimization, Healthy, Information."""
    alerts = {"critical": [], "warning": [], "optimization": [], "healthy": [], "information": []}

    smu = tdata.get("smu", {})
    active = tdata.get("active_sessions", [])
    errors = tdata.get("error_indicators", {})
    compression = tdata.get("compression_health", {})
    session_detail = tdata.get("session_detail", [])
    models = tdata.get("models", [])
    providers = tdata.get("providers", [])
    timeline = tdata.get("timeline", [])
    top_sessions = tdata.get("top_token_sessions", [])

    total_input = safe_num(smu.get("total_input"))
    total_output = safe_num(smu.get("total_output"))
    total_calls = safe_num(smu.get("total_calls"))
    cache_read = safe_num(smu.get("total_cache_read"))
    unique_sessions = safe_num(smu.get("unique_sessions"))
    error_count = safe_num(errors.get("error_sessions"))
    compression_fails = safe_num(compression.get("fails"))
    max_compression_streak = safe_num(compression.get("max_streak"))

    # ── Critical ──────────────────────────────────────────────────

    # API server unreachable
    gw_health = sys_metrics.get("gateway_health", {})
    if gw_health.get("status") == "unreachable":
        alerts["critical"].append({
            "type": "api_server_unreachable",
            "title": "API Server Unreachable",
            "description": "The Hermes API server at port 8642 is not responding. All platform messaging is affected.",
            "evidence": "Health check failed",
            "timestamp": time.time(),
            "severity": "critical",
            "likely_cause": "Gateway process may have stopped or crashed",
            "recommendation": "Check gateway status: hermes doctor. Restart if needed.",
            "is_new": True,
        })

    # High error rate
    total_with_end = safe_num(errors.get("sessions_with_end_reason"))
    error_rate = (error_count / total_with_end * 100) if total_with_end > 0 else 0
    if error_rate > 10:
        alerts["critical"].append({
            "type": "high_error_rate",
            "title": f"High Session Error Rate: {error_rate:.1f}%",
            "description": f"{error_count} out of {total_with_end} completed sessions ended with errors.",
            "evidence": f"Error rate: {error_rate:.1f}% ({error_count}/{total_with_end} sessions)",
            "timestamp": time.time(),
            "severity": "critical",
            "likely_cause": "Provider outages, rate limits, or auth failures",
            "recommendation": "Review recent session errors. Check provider status pages.",
            "is_new": True,
        })

    # ── Warning ───────────────────────────────────────────────────

    # Context limit pressure — per-call average, not cumulative
    for m in models:
        limit = get_context_limit(m["model"])
        if limit > 0 and m["total_calls"] > 0:
            avg_per_call = m["total_input"] / m["total_calls"]
            pct_of_limit = avg_per_call / limit * 100
            if pct_of_limit > 80:
                alerts["warning"].append({
                    "type": "high_avg_context",
                    "title": f"High Average Context per Call: {m['model'][:35]}",
                    "description": f"Average input per API call is {avg_per_call:,.0f} tokens — {pct_of_limit:.0f}% of the {limit:,} token context limit. Individual calls may be approaching the limit.",
                    "evidence": f"{m['total_input']:,} input / {m['total_calls']} calls = {avg_per_call:,.0f} avg per call ({pct_of_limit:.0f}% of {limit:,} limit)",
                    "timestamp": time.time(),
                    "severity": "warning",
                    "likely_cause": "Requests are carrying large context payloads",
                    "recommendation": "Review request context sizes. Consider reducing system prompt or accumulated context.",
                    "is_new": True,
                })

    # Compression failures
    if compression_fails > 10:
        alerts["warning"].append({
            "type": "compression_failures",
            "title": f"Compression Failures: {compression_fails} sessions affected",
            "description": f"{compression_fails} sessions experienced compression failures. Max streak: {max_compression_streak}.",
            "evidence": f"{compression_fails} failures, max streak {max_compression_streak}",
            "timestamp": time.time(),
            "severity": "warning",
            "likely_cause": "Context too large or complex for compression to handle",
            "recommendation": "Review compression failure sessions for patterns.",
            "is_new": True,
        })

    # High input/output ratio
    io_ratio = total_input / total_output if total_output > 0 else float('inf')
    input_pct = total_input / (total_input + total_output) * 100 if (total_input + total_output) > 0 else 100
    if input_pct > 95 and total_calls > 100:
        alerts["warning"].append({
            "type": "input_bound",
            "title": f"System is Highly Input-Bound: {input_pct:.1f}% input share",
            "description": f"Input tokens represent {input_pct:.1f}% of all token volume ({total_input:,} in vs {total_output:,} out). Ratio: {io_ratio:.1f}:1.",
            "evidence": f"{total_input:,} input / {total_output:,} output = {io_ratio:.1f}:1 ratio",
            "timestamp": time.time(),
            "severity": "warning",
            "likely_cause": "Large context windows, accumulated session history, or verbose system prompts",
            "recommendation": "Investigate context accumulation patterns. Check if sessions are persisting unnecessarily large context.",
            "is_new": True,
        })

    # Active sessions without recent activity (tight threshold)
    now_ts = time.time()
    for s in active:
        age = now_ts - (s.get("started_at") or 0)
        dn = s.get("display_name")
        if not dn or dn == "---":
            continue  # skip unnamed sessions
        if age > 7200 and s.get("input_tokens", 0) < 1000:
            alerts["warning"].append({
                "type": "idle_active_session",
                "title": f"Idle Active Session: {dn}",
                "description": f"Session started {format_duration(age)} ago with minimal token usage ({s.get('input_tokens', 0)} input). May be stalled.",
                "evidence": f"Age: {format_duration(age)}, Input: {s.get('input_tokens', 0):,} tokens",
                "timestamp": time.time(),
                "severity": "warning",
                "likely_cause": "Session waiting for input or stalled",
                "recommendation": "Check if session is still needed. Consider closing if idle.",
                "session_id": s["id"],
                "is_new": True,
            })

    # ── Optimization ──────────────────────────────────────────────

    # Low cache efficiency
    cache_pct = (cache_read / total_input * 100) if total_input > 0 else 0
    if cache_pct < 30 and total_input > 1_000_000:
        alerts["optimization"].append({
            "type": "low_cache_efficiency",
            "title": f"Low Cache Efficiency: {cache_pct:.1f}%",
            "description": f"Only {cache_pct:.1f}% of input tokens served from cache. Higher cache usage would reduce token costs.",
            "evidence": f"Cache read: {cache_read:,} / Input: {total_input:,} = {cache_pct:.1f}%",
            "timestamp": time.time(),
            "severity": "optimization",
            "likely_cause": "Cache not being leveraged effectively, or requests have highly variable context",
            "recommendation": "Review caching strategy. Consider repeating identical prompts to leverage cache.",
            "is_new": True,
        })

    # High reasoning consumption
    reasoning = safe_num(smu.get("total_reasoning"))
    if reasoning > total_output * 0.5 and reasoning > 1_000_000:
        reasoning_pct = reasoning / (total_output + reasoning) * 100
        alerts["optimization"].append({
            "type": "high_reasoning_ratio",
            "title": f"High Reasoning Token Ratio: {reasoning_pct:.1f}%",
            "description": f"Reasoning tokens ({reasoning:,}) account for {reasoning_pct:.1f}% of output-like tokens. Model may be spending excess compute on thinking.",
            "evidence": f"Reasoning: {reasoning:,} / Output: {total_output:,} = {reasoning_pct:.1f}%",
            "timestamp": time.time(),
            "severity": "optimization",
            "likely_cause": "Model configured with high reasoning effort or complex tasks",
            "recommendation": "Review if reasoning effort can be reduced for simpler tasks.",
            "is_new": True,
        })

    # Provider concentration
    if providers:
        top_provider = providers[0]
        top_pct = (safe_num(top_provider.get("total_input")) / total_input * 100) if total_input > 0 else 0
        if top_pct > 95 and len(providers) < 3:
            alerts["optimization"].append({
                "type": "provider_concentration",
                "title": f"Heavy Provider Concentration: {top_provider.get('billing_provider') or 'unknown'}",
                "description": f"{top_pct:.1f}% of input tokens go through a single provider. Low provider diversity.",
                "evidence": f"{top_provider.get('billing_provider') or 'unknown'}: {top_pct:.1f}% of {total_input:,} input tokens",
                "timestamp": time.time(),
                "severity": "optimization",
                "likely_cause": "Single provider configured as primary",
                "recommendation": "Consider configuring fallback providers for resilience.",
                "is_new": True,
            })

    # ── Healthy ───────────────────────────────────────────────────

    if error_rate == 0 and total_with_end > 0:
        alerts["healthy"].append({
            "type": "no_errors",
            "title": "No Session Errors",
            "description": f"All {total_with_end} completed sessions finished without errors.",
            "evidence": f"0 errors across {total_with_end} sessions",
            "timestamp": time.time(),
            "severity": "healthy",
            "is_new": False,
        })

    if cache_pct > 60 and total_input > 1_000_000:
        alerts["healthy"].append({
            "type": "good_cache",
            "title": f"Strong Cache Performance: {cache_pct:.1f}% hit rate",
            "description": f"Cache is serving {cache_pct:.1f}% of input tokens, reducing token consumption significantly.",
            "evidence": f"{cache_read:,} cache hits / {total_input:,} input = {cache_pct:.1f}%",
            "timestamp": time.time(),
            "severity": "healthy",
            "is_new": False,
        })

    # ── Information ───────────────────────────────────────────────

    # Provider distribution info
    if providers:
        for p in providers[:3]:
            pct = (safe_num(p.get("total_input")) / total_input * 100) if total_input > 0 else 0
            alerts["information"].append({
                "type": "provider_usage",
                "title": f"Provider: {p.get('billing_provider') or 'unknown'} — {pct:.1f}% share",
                "description": f"{safe_num(p.get('total_input')):,} input tokens across {p.get('sessions')} sessions, {p.get('total_calls')} API calls.",
                "evidence": f"{safe_num(p.get('total_input')):,} tokens, {p.get('sessions')} sessions",
                "timestamp": time.time(),
                "severity": "information",
                "is_new": False,
            })

    # Model usage info
    for m in models[:3]:
        pct = (safe_num(m.get("total_input")) / total_input * 100) if total_input > 0 else 0
        alerts["information"].append({
            "type": "model_usage",
            "title": f"Model: {m['model'][:35]} — {pct:.1f}% of input",
            "description": f"{safe_num(m.get('total_input')):,} input tokens, {safe_num(m.get('total_output')):,} output, {m['sessions']} sessions.",
            "evidence": f"{safe_num(m.get('total_input')):,} tokens across {m['sessions']} sessions",
            "timestamp": time.time(),
            "severity": "information",
            "is_new": False,
        })

    # Active session info
    if active:
        for s in active[:5]:
            age = now_ts - (s.get("started_at") or 0)
            alerts["information"].append({
                "type": "active_session",
                "title": f"Active: {s.get('display_name', 'Unknown')} — {(s.get('model') or 'unknown')[:30]}",
                "description": f"Running {format_duration(age)}, {s.get('input_tokens', 0):,} input, {s.get('output_tokens', 0):,} output, {s.get('message_count', 0)} messages.",
                "evidence": f"Age: {format_duration(age)}, Input: {s.get('input_tokens', 0):,}",
                "timestamp": time.time(),
                "severity": "information",
                "is_new": False,
                "session_id": s["id"],
            })

    return alerts


def compute_alfred_insights(tdata):
    """Derive measurable observations, then interpret them."""
    smu = tdata.get("smu", {})
    providers = tdata.get("providers", [])
    models = tdata.get("models", [])
    session_detail = tdata.get("session_detail", [])
    timeline = tdata.get("timeline", [])

    total_input = safe_num(smu.get("total_input"))
    total_output = safe_num(smu.get("total_output"))
    total_calls = safe_num(smu.get("total_calls"))
    total_cache = safe_num(smu.get("total_cache_read"))
    total_reasoning = safe_num(smu.get("total_reasoning"))
    unique_sessions = safe_num(smu.get("unique_sessions"))
    total_sessions = safe_num(tdata.get("sessions_summary", {}).get("session_count"))

    insights = []

    # ── Observation 1: Input dominance ───────────────────────────
    input_pct = total_input / (total_input + total_output) * 100 if (total_input + total_output) > 0 else 100
    io_ratio = total_input / total_output if total_output > 0 else float('inf')

    observation = f"Input tokens represent {input_pct:.1f}% of total token volume."
    evidence_items = [
        f"Total input: {total_input:,} tokens",
        f"Total output: {total_output:,} tokens",
        f"Input/output ratio: {io_ratio:.1f}:1",
        f"Across {total_calls:,} API calls",
    ]
    interpretation = (
        f"Hermes is spending the overwhelming majority of its token budget processing context "
        f"rather than generating responses. For every 1 token of output, approximately {io_ratio:.0f} "
        f"tokens of input are being processed."
    )
    impact = (
        f" token consumption is heavily weighted toward input processing. This means context size, "
        f"session persistence, and system prompt design have an outsized impact on resource usage. "
        f"Even small reductions in average context per request would yield significant savings."
    )
    decision = (
        "Investigate session context accumulation patterns. Review whether sessions are carrying "
        "unnecessarily large context between requests. Consider context truncation, session rotation, "
        "or system prompt optimization before adding more model capacity."
    )

    insights.append({
        "observation": observation,
        "evidence": evidence_items,
        "interpretation": interpretation,
        "impact": impact,
        "decision": decision,
        "category": "efficiency",
        "severity": "warning",
        "drilldown_path": ["providers", "models", "sessions"],
    })

    # ── Observation 2: Provider distribution ─────────────────────
    if providers:
        top_provider = providers[0]
        top_pct = (safe_num(top_provider.get("total_input")) / total_input * 100) if total_input > 0 else 0
        top_provider_name = top_provider.get("billing_provider") or "unknown"

        provider_evidence = []
        for p in providers:
            pct = (safe_num(p.get("total_input")) / total_input * 100) if total_input > 0 else 0
            provider_evidence.append(
                f"{p.get('billing_provider') or 'unknown'}: {pct:.1f}% ({safe_num(p.get('total_input')):,} tokens, {p.get('sessions')} sessions)"
            )

        insights.append({
            "observation": f"{top_provider_name} accounts for {top_pct:.1f}% of all input token consumption.",
            "evidence": provider_evidence,
            "interpretation": (
                f"Token consumption is heavily concentrated through a single provider. "
                f"This creates dependency on {top_provider_name}'s availability, pricing, and rate limits. "
                f"Failover to other providers is minimal."
            ),
            "impact": (
                f" Provider concentration means service disruptions or rate limits on {top_provider_name} "
                f"would affect the majority of Hermes operations. Diversification would improve resilience."
            ),
            "decision": (
                "Review provider configuration. Ensure fallback providers are configured and tested. "
                "Consider whether the primary provider choice is still optimal for cost and reliability."
            ),
            "category": "resilience",
            "severity": "info",
            "drilldown_path": ["providers", "models"],
        })

    # ── Observation 3: Cache effectiveness ───────────────────────
    cache_pct = (total_cache / total_input * 100) if total_input > 0 else 0

    if cache_pct > 50:
        cache_interpretation = (
            f"Cache is performing well, serving {cache_pct:.1f}% of input tokens from cached responses. "
            f"This significantly reduces token costs for repeated or similar prompts."
        )
        cache_decision = "Cache strategy is effective. Continue monitoring to ensure it stays above 50%."
        cache_severity = "healthy"
    elif cache_pct > 20:
        cache_interpretation = (
            f"Cache serves {cache_pct:.1f}% of input tokens — moderate effectiveness. "
            f"There is room to improve cache utilization through more consistent prompt patterns."
        )
        cache_decision = (
            "Consider standardizing prompt formats where possible to increase cache hit rates. "
            "Small improvements in cache efficiency yield direct token savings."
        )
        cache_severity = "optimization"
    else:
        cache_interpretation = (
            f"Cache serves only {cache_pct:.1f}% of input tokens — low effectiveness. "
            f"The majority of input tokens are being processed fresh each time."
        )
        cache_decision = (
            "Review caching strategy. If prompts are highly variable, consider whether some can be "
            "standardized. If cache is unavailable, investigate provider cache configuration."
        )
        cache_severity = "warning"

    insights.append({
        "observation": f"Cache serves {cache_pct:.1f}% of input tokens ({total_cache:,} / {total_input:,}).",
        "evidence": [
            f"Cache read tokens: {total_cache:,}",
            f"Total input tokens: {total_input:,}",
            f"Cache hit rate: {cache_pct:.1f}%",
        ],
        "interpretation": cache_interpretation,
        "impact": (
            f" Cache effectiveness directly impacts token costs. "
            f"{'High cache usage is reducing costs significantly.' if cache_pct > 50 else 'Low cache usage means more tokens are billed for each request.'}"
        ),
        "decision": cache_decision,
        "category": "efficiency",
        "severity": cache_severity,
        "drilldown_path": ["models", "sessions"],
    })

    # ── Observation 4: Usage trajectory ──────────────────────────
    last7 = tdata.get("last_7_days", {})
    prev7 = tdata.get("prev_7_days", {})
    l7_calls = safe_num(last7.get("calls"))
    p7_calls = safe_num(prev7.get("calls"))
    l7_in = safe_num(last7.get("input"))
    p7_in = safe_num(prev7.get("input"))

    if p7_calls > 0:
        call_delta = pct_change(l7_calls, p7_calls)
        in_delta = pct_change(l7_in, p7_in)

        if call_delta is not None and in_delta is not None:
            trajectory_observation = (
                f"API call volume changed {call_delta:+.1f}% week-over-week, "
                f"while input tokens changed {in_delta:+.1f}%."
            )
            trajectory_evidence = [
                f"Last 7 days: {l7_calls:,} calls, {l7_in:,} input tokens",
                f"Previous 7 days: {p7_calls:,} calls, {p7_in:,} input tokens",
                f"Call volume delta: {call_delta:+.1f}%",
                f"Input token delta: {in_delta:+.1f}%",
            ]

            if in_delta > call_delta * 1.5 and in_delta > 10:
                trajectory_interpretation = (
                    f"Input tokens are growing faster than request volume ({in_delta:+.1f}% vs {call_delta:+.1f}%). "
                    f"This suggests average request context size is increasing — each request is carrying more context "
                    f"than it was a week ago."
                )
                trajectory_decision = (
                    "Investigate whether session context is growing over time. Check if long-running sessions "
                    "are accumulating context without bounds. Review context truncation settings."
                )
                trajectory_severity = "warning"
            elif in_delta < -10 and call_delta < -10:
                trajectory_interpretation = (
                    f"Both request volume and token consumption are decreasing ({call_delta:+.1f}% and {in_delta:+.1f}%). "
                    f"System activity is declining."
                )
                trajectory_decision = "No action needed unless this reflects an unintended service reduction."
                trajectory_severity = "info"
            else:
                trajectory_interpretation = (
                    f"Token consumption and request volume are moving roughly in parallel. "
                    f"The system is scaling proportionally."
                )
                trajectory_decision = "No specific action required. Continue monitoring."
                trajectory_severity = "info"

            insights.append({
                "observation": trajectory_observation,
                "evidence": trajectory_evidence,
                "interpretation": trajectory_interpretation,
                "impact": (
                    " Understanding whether token growth is driven by more requests or larger contexts "
                    "determines the right intervention."
                ),
                "decision": trajectory_decision,
                "category": "trend",
                "severity": trajectory_severity,
                "drilldown_path": ["timeline", "sessions"],
            })

    # ── Observation 5: Session efficiency ────────────────────────
    if session_detail:
        avg_input_per_session = total_input / len(session_detail) if session_detail else 0
        avg_calls_per_session = total_calls / len(session_detail) if session_detail else 0

        # Top 3 most token-intensive sessions
        top3 = sorted(session_detail, key=lambda s: s.get("input_tokens", 0) or 0, reverse=True)[:3]
        top3_evidence = []
        for s in top3:
            top3_evidence.append(
                f"{s.get('display_name') or s.get('session_id', '?')[:30]}: {s.get('input_tokens', 0):,} input, "
                f"{s.get('output_tokens', 0):,} output, {s.get('api_call_count', 0)} calls, "
                f"model: {(s.get('model') or '?')[:30]}"
            )

        insights.append({
            "observation": f"Average {avg_input_per_session:,.0f} input tokens per session-model combo across {len(session_detail)} records.",
            "evidence": [
                f"Total sessions-model combos: {len(session_detail)}",
                f"Average input per combo: {avg_input_per_session:,.0f} tokens",
                f"Average API calls per combo: {avg_calls_per_session:.1f}",
                "Top 3 most token-intensive:",
            ] + top3_evidence,
            "interpretation": (
                f"Session context sizes vary significantly. The top consumers may represent unusually large contexts "
                f"or long-running sessions. Understanding what drives top-session consumption helps identify "
                f"optimization targets."
            ),
            "impact": (
                f" A small number of sessions may account for a disproportionate share of token usage. "
                f"Optimizing these yields outsized benefits."
            ),
            "decision": (
                "Review the top 5 highest-token sessions. Determine whether their context size is justified "
                "by the task complexity, or whether context could be reduced without impacting quality."
            ),
            "category": "efficiency",
            "severity": "info",
            "drilldown_path": ["sessions", "models"],
        })

    return insights


def compute_decision_queue(tdata, alerts):
    """Build prioritized decision queue from alerts and insights."""
    decisions = []

    # Critical decisions from critical alerts
    for a in alerts.get("critical", []):
        decisions.append({
            "priority": "critical",
            "icon": "🔴",
            "title": a["title"],
            "why": a["description"],
            "evidence": a["evidence"],
            "recommended_action": a["recommendation"],
            "severity": "critical",
            "alert_type": a["type"],
        })

    # Warning decisions from warning alerts
    for a in alerts.get("warning", []):
        decisions.append({
            "priority": "warning",
            "icon": "🟠",
            "title": a["title"],
            "why": a["description"],
            "evidence": a["evidence"],
            "recommended_action": a["recommendation"],
            "severity": "warning",
            "alert_type": a["type"],
        })

    # Optimization decisions from optimization alerts
    for a in alerts.get("optimization", []):
        decisions.append({
            "priority": "optimization",
            "icon": "🟡",
            "title": a["title"],
            "why": a["description"],
            "evidence": a["evidence"],
            "recommended_action": a["recommendation"],
            "severity": "optimization",
            "alert_type": a["type"],
        })

    # Decisions from Alfred insights
    insights = tdata.get("alfred_insights", [])
    for ins in insights:
        if ins.get("severity") in ("warning", "optimization"):
            decisions.append({
                "priority": ins.get("severity", "info"),
                "icon": "🟠" if ins.get("severity") == "warning" else "🟡",
                "title": ins["observation"],
                "why": ins["interpretation"],
                "evidence": ins["evidence"][:2],
                "recommended_action": ins["decision"],
                "severity": ins.get("severity", "info"),
                "is_insight": True,
                "category": ins.get("category", "general"),
            })

    # Healthy / no-action items
    for a in alerts.get("healthy", []):
        decisions.append({
            "priority": "healthy",
            "icon": "🟢",
            "title": a["title"],
            "why": a["description"],
            "evidence": a["evidence"],
            "recommended_action": "No action required.",
            "severity": "healthy",
            "alert_type": a["type"],
        })

    # Sort: critical first, then warning, then optimization, then healthy
    priority_order = {"critical": 0, "warning": 1, "optimization": 2, "healthy": 3, "info": 4}
    decisions.sort(key=lambda d: priority_order.get(d["priority"], 5))

    return decisions


def compute_activity_timeline(tdata):
    """Build chronological activity feed from session data."""
    session_detail = tdata.get("session_detail", [])
    timeline = tdata.get("timeline", [])

    events = []

    # Sort sessions by first_seen
    sessions_sorted = sorted(session_detail, key=lambda s: s.get("first_seen") or 0)

    for s in sessions_sorted:
        ts = s.get("first_seen") or 0
        if not ts:
            continue
        time_str = datetime.datetime.fromtimestamp(ts).strftime("%H:%M")

        display = s.get("display_name") or infer_display(s.get("session_key", ""))
        model = s.get("model", "?")
        platform = infer_platform(s.get("session_key", ""))
        input_tok = s.get("input_tokens", 0) or 0
        output_tok = s.get("output_tokens", 0) or 0
        api_calls = s.get("api_call_count", 0) or 0
        cache_read = s.get("cache_read_tokens", 0) or 0
        reasoning = s.get("reasoning_tokens", 0) or 0
        messages = s.get("message_count", 0) or 0
        tools = s.get("tool_call_count", 0) or 0
        title = s.get("title") or ""

        # Determine event type
        if api_calls > 50:
            event_type = "heavy_session"
            description = (
                f"Heavy session: {display} used {model[:25]} with {input_tok:,} input, "
                f"{output_tok:,} output across {api_calls} API calls"
            )
        elif input_tok > 1_000_000:
            event_type = "large_context"
            description = (
                f"Large context session: {display} processed {input_tok:,} input tokens "
                f"on {model[:25]}"
            )
        elif cache_read > input_tok * 0.5:
            event_type = "cache_heavy"
            description = (
                f"Cache-efficient session: {display} received {cache_read:,} cache reads "
                f"({cache_read/input_tok*100:.0f}% of input) on {model[:25]}"
            )
        elif reasoning > output_tok * 0.5 and reasoning > 10000:
            event_type = "reasoning_heavy"
            description = (
                f"Reasoning-heavy session: {display} used {reasoning:,} reasoning tokens "
                f"on {model[:25]}"
            )
        elif tools > 5:
            event_type = "tool_use"
            description = (
                f"Tool-using session: {display} made {tools} tool calls during {messages} messages "
                f"on {model[:25]}"
            )
        else:
            event_type = "session"
            description = (
                f"Session: {display} on {model[:25]} — {input_tok:,} in, {output_tok:,} out, "
                f"{api_calls} API calls, {messages} messages"
            )

        events.append({
            "timestamp": ts,
            "time_str": time_str,
            "event_type": event_type,
            "title": display,
            "description": description,
            "model": model,
            "platform": platform,
            "input_tokens": input_tok,
            "output_tokens": output_tok,
            "api_calls": api_calls,
            "cache_read": cache_read,
            "reasoning": reasoning,
            "messages": messages,
            "tool_calls": tools,
            "title_text": title,
            "session_id": s.get("session_id"),
            "billing_provider": s.get("billing_provider"),
        })

    # Sort by timestamp descending (most recent first)
    events.sort(key=lambda e: e["timestamp"], reverse=True)

    # Limit to most recent 200 events for performance
    return events[:200]


def compute_anomalies(tdata):
    """Detect statistically or operationally meaningful anomalies."""
    anomalies = []
    timeline = tdata.get("timeline", [])
    session_detail = tdata.get("session_detail", [])
    models = tdata.get("models", [])

    if not timeline:
        return anomalies

    # ── Token spike detection ─────────────────────────────────────
    inputs = [t.get("input", 0) or 0 for t in timeline if t.get("input")]
    if len(inputs) >= 5:
        avg = mean(inputs)
        std = stdev(inputs) if len(inputs) > 1 else 0
        threshold = avg + std * 2.5 if std > 0 else avg * 3

        for t in timeline:
            inp = t.get("input", 0) or 0
            if inp > threshold and inp > 100_000:
                anomalies.append({
                    "type": "token_spike",
                    "severity": "warning",
                    "timestamp": t.get("hour_ts"),
                    "time_str": t.get("hour_label"),
                    "title": f"Token Spike: {t.get('hour_label')}",
                    "description": f"{inp:,} input tokens in one hour — {inp/avg:.1f}x the average ({avg:,.0f}).",
                    "evidence": f"Hourly input: {inp:,} vs avg {avg:,.0f} (threshold: {threshold:,.0f})",
                    "likely_cause": "Large batch of requests or unusually large context windows",
                    "recommendation": "Review sessions active during this hour for context size patterns.",
                })

    # ── API call spike detection ──────────────────────────────────
    # (We don't have per-hour API call counts in timeline, but we can use sessions per hour)
    session_counts = [t.get("sessions", 0) or 0 for t in timeline]
    if len(session_counts) >= 5:
        avg_s = mean(session_counts)
        std_s = stdev(session_counts) if len(session_counts) > 1 else 0
        threshold_s = avg_s + std_s * 2.5 if std_s > 0 else avg_s * 3

        for t in timeline:
            sc = t.get("sessions", 0) or 0
            if sc > threshold_s and sc > 3:
                anomalies.append({
                    "type": "session_spike",
                    "severity": "info",
                    "timestamp": t.get("hour_ts"),
                    "time_str": t.get("hour_label"),
                    "title": f"Session Volume Spike: {t.get('hour_label')}",
                    "description": f"{sc} sessions active in one hour — {sc/avg_s:.1f}x the average ({avg_s:.1f}).",
                    "evidence": f"Hourly sessions: {sc} vs avg {avg_s:.1f}",
                    "likely_cause": "Period of high user activity",
                    "recommendation": None,
                })

    # ── Unusual model switches ────────────────────────────────────
    # Detect sessions using models that are rare in the dataset
    model_counts = {}
    for s in session_detail:
        m = s.get("model")
        if m:
            model_counts[m] = model_counts.get(m, 0) + 1

    total_session_records = len(session_detail)
    for m, count in model_counts.items():
        if count == 1 and total_session_records > 10:
            # Single-use model — could be experimental or fallback
            s = next((x for x in session_detail if x.get("model") == m), None)
            if s:
                anomalies.append({
                    "type": "rare_model_usage",
                    "severity": "info",
                    "timestamp": s.get("first_seen"),
                    "time_str": fmt_ts(s.get("first_seen")),
                    "title": f"Single-Use Model: {m[:40]}",
                    "description": f"Model {m[:40]} was used in only 1 session-model combo out of {total_session_records}.",
                    "evidence": f"1 session, {s.get('input_tokens', 0):,} input, {s.get('output_tokens', 0):,} output",
                    "likely_cause": "Experimental usage, fallback, or one-off task",
                    "recommendation": None,
                    "session_id": s.get("session_id"),
                })

    # ── Large individual requests ─────────────────────────────────
    for s in session_detail:
        if s.get("input_tokens", 0) and s.get("input_tokens", 0) > 500_000:
            anomalies.append({
                "type": "large_request_session",
                "severity": "info",
                "timestamp": s.get("first_seen"),
                "time_str": fmt_ts(s.get("first_seen")),
                "title": f"Very Large Session: {(s.get('display_name') or 'Unknown')[:30]}",
                "description": f"Session processed {s.get('input_tokens', 0):,} input tokens — very large context.",
                "evidence": f"{s.get('input_tokens', 0):,} input, {s.get('output_tokens', 0):,} output, {s.get('api_call_count', 0)} calls",
                "likely_cause": "Complex task with large context requirements",
                "recommendation": "Review whether context can be reduced for similar future tasks.",
                "session_id": s.get("session_id"),
            })

    return anomalies


def compute_alfred_briefing(tdata, sys_status, alerts):
    """Generate a concise daily/periodic briefing."""
    smu = tdata.get("smu", {})
    last7 = tdata.get("last_7_days", {})
    prev7 = tdata.get("prev_7_days", {})

    total_input = safe_num(smu.get("total_input"))
    total_output = safe_num(smu.get("total_output"))
    total_calls = safe_num(smu.get("total_calls"))
    active = len(tdata.get("active_sessions", []))

    # Activity assessment
    if total_calls == 0:
        activity = "No activity"
    elif total_calls < 50:
        activity = "Very low"
    elif total_calls < 200:
        activity = "Low"
    elif total_calls < 1000:
        activity = "Moderate"
    elif total_calls < 5000:
        activity = "High"
    else:
        activity = "Very high"

    # Usage trend
    l7_calls = safe_num(last7.get("calls"))
    p7_calls = safe_num(prev7.get("calls"))
    l7_in = safe_num(last7.get("input"))
    p7_in = safe_num(prev7.get("input"))

    call_delta = pct_change(l7_calls, p7_calls)
    in_delta = pct_change(l7_in, p7_in)

    usage_trend = "→ stable"
    if call_delta is not None:
        if call_delta > 20:
            usage_trend = f"↑ {call_delta:.0f}%"
        elif call_delta > 5:
            usage_trend = f"↑ {call_delta:.0f}%"
        elif call_delta < -20:
            usage_trend = f"↓ {abs(call_delta):.0f}%"
        elif call_delta < -5:
            usage_trend = f"↓ {abs(call_delta):.0f}%"

    efficiency_trend = "→ stable"
    if in_delta is not None and call_delta is not None and p7_calls > 0:
        if in_delta > call_delta * 1.5 and in_delta > 10:
            efficiency_trend = f"↓ {in_delta - call_delta:.0f}pp (input growing faster)"
        elif in_delta < call_delta - 10:
            efficiency_trend = f"↑ context per request declining"
        elif abs(in_delta - call_delta) < 5:
            efficiency_trend = "→ proportional"

    # Error assessment
    errors = tdata.get("error_indicators", {})
    error_count = safe_num(errors.get("error_sessions"))
    total_with_end = safe_num(errors.get("sessions_with_end_reason"))
    error_rate = (error_count / total_with_end * 100) if total_with_end > 0 else 0

    if error_rate == 0:
        error_status = "Normal"
    elif error_rate < 3:
        error_status = "Low"
    elif error_rate < 10:
        error_status = "Elevated"
    else:
        error_status = "High"

    # Biggest change
    biggest_change = "No significant change detected"
    if in_delta is not None and abs(in_delta) > 10:
        biggest_change = f"Input token consumption changed {in_delta:+.1f}% ({l7_in:,.0f} vs {p7_in:,.0f} tokens)"
    elif call_delta is not None and abs(call_delta) > 15:
        biggest_change = f"API call volume changed {call_delta:+.1f}% ({l7_calls:,.0f} vs {p7_calls:,.0f} calls)"
    elif in_delta is not None or call_delta is not None:
        # Even if not "significant", show the actual delta
        parts = []
        if in_delta is not None:
            parts.append(f"input {in_delta:+.1f}%")
        if call_delta is not None:
            parts.append(f"calls {call_delta:+.1f}%")
        biggest_change = "Usage shifted: " + ", ".join(parts) + " vs prior period"

    # Biggest concern
    concerns = []
    if in_delta is not None and in_delta > 20:
        concerns.append("Input token consumption is growing significantly")
    if error_rate > 5:
        concerns.append(f"Error rate is elevated at {error_rate:.1f}%")
    if total_input > 0 and safe_num(smu.get("total_cache_read")) / total_input < 0.3:
        concerns.append("Cache efficiency is low")
    if not concerns:
        concerns.append("No major concerns — system operating normally")

    # Biggest opportunity
    opportunities = []
    if safe_num(smu.get("total_cache_read")) / total_input < 0.5 and total_input > 1_000_000:
        opportunities.append("Improve cache strategy to reduce token costs")
    if total_input / total_output > 50 and total_output > 0:
        opportunities.append("Reduce context per request to improve efficiency")
    if len(tdata.get("providers", [])) < 3:
        opportunities.append("Add provider diversity for resilience")
    if not opportunities:
        opportunities.append("Continue monitoring for optimization opportunities")

    # Recommended action
    recommended = "Continue monitoring"
    if in_delta is not None and in_delta > 20:
        recommended = "Investigate top sessions by token consumption"
    elif error_rate > 5:
        recommended = "Review recent session errors"
    elif safe_num(smu.get("total_cache_read")) / total_input < 0.3:
        recommended = "Review caching configuration and prompt patterns"

    # Critical alerts count
    critical_count = len(alerts.get("critical", []))
    warning_count = len(alerts.get("warning", []))

    return {
        "system_status": sys_status["overall_label"],
        "activity": activity,
        "usage_trend": usage_trend,
        "efficiency_trend": efficiency_trend,
        "error_status": error_status,
        "biggest_change": biggest_change,
        "biggest_concern": concerns[0],
        "biggest_opportunity": opportunities[0],
        "recommended_action": recommended,
        "critical_count": critical_count,
        "warning_count": warning_count,
        "total_input": total_input,
        "total_output": total_output,
        "total_calls": total_calls,
        "active_sessions": active,
    }


# ── Intelligence API (single endpoint for all intelligence data) ──

def compute_all_intelligence():
    """Compute and return the complete intelligence payload."""
    tdata = get_telemetry_data()
    sys_metrics = get_system_metrics()

    # Compute all intelligence layers
    sys_status = compute_system_status(tdata, sys_metrics)
    what_changed = compute_what_changed(tdata)
    attention = compute_attention_required(tdata, sys_metrics)
    insights = compute_alfred_insights(tdata)
    decisions = compute_decision_queue(tdata, attention)
    timeline = compute_activity_timeline(tdata)
    anomalies = compute_anomalies(tdata)
    briefing = compute_alfred_briefing(tdata, sys_status, attention)

    # Attach insights to tdata for decision queue
    tdata["alfred_insights"] = insights

    # Re-compute decisions with insights attached
    decisions = compute_decision_queue(tdata, attention)

    return {
        "system_status": sys_status,
        "what_changed": what_changed,
        "attention_required": attention,
        "alfred_insights": insights,
        "decision_queue": decisions,
        "activity_timeline": timeline,
        "anomalies": anomalies,
        "daily_briefing": briefing,
        "updated_at": time.time(),
        # Raw telemetry for drill-down
        "raw": {
            "total_input": safe_num(tdata.get("smu", {}).get("total_input")),
            "total_output": safe_num(tdata.get("smu", {}).get("total_output")),
            "total_calls": safe_num(tdata.get("smu", {}).get("total_calls")),
            "total_cache_read": safe_num(tdata.get("smu", {}).get("total_cache_read")),
            "total_reasoning": safe_num(tdata.get("smu", {}).get("total_reasoning")),
            "unique_sessions": safe_num(tdata.get("smu", {}).get("unique_sessions")),
            "total_sessions": safe_num(tdata.get("sessions_summary", {}).get("session_count")),
            "active_sessions": len(tdata.get("active_sessions", [])),
            "providers": [
                {
                    "provider": p.get("billing_provider") or "unknown",
                    "input_tokens": safe_num(p.get("total_input")),
                    "output_tokens": safe_num(p.get("total_output")),
                    "cache_read": safe_num(p.get("total_cache_read")),
                    "api_calls": safe_num(p.get("total_calls")),
                    "sessions": p.get("sessions"),
                } for p in tdata.get("providers", [])
            ],
            "models": [
                {
                    "model": m["model"],
                    "billing_provider": m.get("billing_provider"),
                    "input_tokens": safe_num(m.get("total_input")),
                    "output_tokens": safe_num(m.get("total_output")),
                    "cache_read": safe_num(m.get("total_cache_read")),
                    "reasoning": safe_num(m.get("total_reasoning")),
                    "api_calls": safe_num(m.get("total_calls")),
                    "sessions": m.get("sessions"),
                    "context_limit": get_context_limit(m["model"]),
                } for m in tdata.get("models", [])
            ],
            "top_sessions": [
                {
                    "session_id": s.get("session_id"),
                    "display_name": s.get("display_name"),
                    "platform": infer_platform(s.get("session_key", "")),
                    "model": s.get("model"),
                    "input_tokens": safe_num(s.get("input_tokens")),
                    "output_tokens": safe_num(s.get("output_tokens")),
                    "cache_read": safe_num(s.get("cache_read_tokens")),
                    "reasoning": safe_num(s.get("reasoning_tokens")),
                    "api_calls": safe_num(s.get("api_call_count")),
                    "messages": safe_num(s.get("message_count")),
                    "title": s.get("title"),
                    "context_limit": get_context_limit(s.get("model")),
                } for s in tdata.get("top_token_sessions", [])
            ],
            "error_indicators": tdata.get("error_indicators", {}),
            "compression_health": tdata.get("compression_health", {}),
        }
    }


if __name__ == "__main__":
    result = compute_all_intelligence()
    print(json.dumps(result, indent=2, default=str)[:5000])
    print(f"\n... (total {len(json.dumps(result))} bytes)")
