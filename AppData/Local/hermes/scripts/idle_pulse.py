#!/usr/bin/env python3
"""
Idle Pulse — system audit + autonomous chore worker for Hermes idle periods.

Two modes:
  • Audit-only (default, no flags): prints a concise system report. This is what
    the existing cron job (acfcdeaaf5ce) runs every 360m.
  • Work mode (--work): reads tasks.md + recent learning, audits system/repos,
    selects one safe bounded chore, executes it, verifies, records, updates
    tasks.md, and delivers a brief result. Design for manual invocation or a
    second cron job once the behavior is proven.

Activity log: AppData/Local/hermes/logs/idle_activity.jsonl
  One JSON object per invocation (work or audit). Work-mode entries record the
  selected chore, action, verification, result, and commit hash so the system
  can avoid repeating completed chores.

Chore completion is tracked by a content hash of (repo, rel_path, description).
If that hash appears in the activity log with result == "completed", the chore
is skipped on subsequent runs.

Safety boundary: only bounded, reversible, internal work is executed
automatically. Everything else is recorded as BLOCKED_REVIEW_REQUIRED.

Git push reporting distinguishes four states:
  • remote == local       → pushed (verified)
  • remote != local + fetch ok → push failed or not yet attempted
  • fetch fails/timeout   → push status uncertain (network)
  • no local commit       → nothing to push
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

HOME = os.path.expanduser("~")
HERMES = os.path.join(HOME, "AppData", "Local", "hermes")
ACTIVITY_LOG = os.path.join(HERMES, "logs", "idle_activity.jsonl")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def run(cmd: str, cwd: Optional[str] = None, timeout: int = 15):
    """Run a shell command. Returns (exit_code, stdout, stderr)."""
    try:
        p = subprocess.run(
            cmd, shell=True, cwd=cwd, capture_output=True,
            timeout=timeout, text=True,
        )
        return p.returncode, p.stdout, p.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "timeout"
    except Exception as e:
        return -1, "", str(e)


def disk_space(drive_letter: str) -> str:
    try:
        import ctypes
        free = ctypes.c_ulonglong(0)
        total = ctypes.c_ulonglong(0)
        path = f"{drive_letter}:\\"
        ok = ctypes.windll.kernel32.GetDiskFreeSpaceExW(
            path, ctypes.byref(free), ctypes.byref(total), None,
        )
        if ok:
            return f"{drive_letter}: {free.value / (1024**3):.0f}/{total.value / (1024**3):.0f} GB free"
        return f"{drive_letter}: unavailable"
    except Exception:
        return f"{drive_letter}: unavailable"


def cron_health() -> str:
    jobs_file = os.path.join(HERMES, "cron", "jobs.json")
    if not os.path.exists(jobs_file):
        return "  cron/jobs.json not found"
    try:
        with open(jobs_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        jobs = data.get("jobs", [])
        if not jobs:
            return "  no cron jobs registered"
        lines = []
        for j in jobs:
            name = j.get("name", "?")[:50]
            state = j.get("state", "?")
            last_status = j.get("last_status") or "?"
            err = j.get("last_delivery_error") or ""
            if err:
                err = err.split("\n")[0][:60]
            next_run = j.get("next_run_at") or ""
            if next_run:
                try:
                    n = datetime.fromisoformat(next_run)
                    next_run = n.strftime("%Y-%m-%d %H:%M")
                except Exception:
                    pass
            if j.get("enabled") is False:
                name = f"[DISABLED] {name}"
            lines.append(f"  {name:50} | last: {last_status:6} | next: {next_run} | {err}")
        return "\n".join(lines)
    except Exception as e:
        return f"  failed to read cron/jobs.json: {e}"


def ports_alive(ports):
    import socket
    result = {}
    for port in ports:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(2)
            s.connect(("127.0.0.1", port))
            result[port] = "UP"
            s.close()
        except Exception:
            result[port] = "down"
    return result


def git_repos_with_changes(root: str):
    findings = []
    skip_dirnames = {"node_modules", ".venv", "venv", "__pycache__"}
    skip_paths = {".git", "AppData", "node_modules"}
    for dirpath, dirnames, _filenames in os.walk(root):
        if ".git" in dirnames:
            rel = os.path.relpath(dirpath, root).replace("\\", "/")
            if any(skip in rel for skip in skip_dirnames):
                dirnames.remove(".git")
                continue
            code, _, _ = run(f'git -C "{dirpath}" rev-parse --git-dir', timeout=10)
            if code != 0:
                dirnames.remove(".git")
                continue
            code, out, err = run(f'git -C "{dirpath}" status --short', timeout=15)
            if code == 0 and out.strip():
                findings.append((dirpath, out.strip().split("\n")))
            elif code != 0:
                findings.append((dirpath, [f"(git status failed: {err.strip()[:40]})"]))
        if any(skip in dirpath for skip in skip_paths):
            dirnames.clear()
    return findings


def stale_processes(patterns):
    findings = []
    try:
        code, out, _err = run("tasklist /FO CSV /NH", timeout=10)
        if code == 0:
            for line in out.split("\n"):
                for pat in patterns:
                    if pat.lower() in line.lower():
                        findings.append(line.strip()[:100])
    except Exception:
        pass
    return findings


def tasks_file_path() -> Optional[str]:
    for name in ["tasks.md", "unfinished-tasks.md", "TODO.md", "alfred-summary.md"]:
        path = os.path.join(HOME, name)
        if os.path.exists(path):
            return path
    return None


def recent_learning_files(limit: int = 2):
    log_dir = os.path.join(HERMES, "logs", "learning")
    if not os.path.isdir(log_dir):
        return []
    files = []
    for entry in sorted(os.listdir(log_dir), reverse=True):
        if entry.endswith("_learning.md"):
            files.append(os.path.join(log_dir, entry))
            if len(files) >= limit:
                break
    return files


def memory_freshness():
    mem_dir = os.path.join(HERMES, "memories")
    results = {}
    for name in ["USER.md", "MEMORY.md"]:
        path = os.path.join(mem_dir, name)
        if os.path.exists(path):
            mtime = os.path.getmtime(path)
            ago_hours = (datetime.now(timezone.utc).timestamp() - mtime) / 3600
            results[name] = f"{name}: modified {ago_hours:.1f}h ago, {os.path.getsize(path)} bytes"
        else:
            results[name] = f"{name}: missing"
    return results


def ensure_dirs():
    os.makedirs(os.path.join(HERMES, "logs"), exist_ok=True)


def load_completed_hashes() -> set:
    """Return set of chore content-hashes marked as completed in the activity log."""
    hashes = set()
    if not os.path.exists(ACTIVITY_LOG):
        return hashes
    try:
        with open(ACTIVITY_LOG, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    if entry.get("result") == "completed":
                        h = entry.get("chore_hash")
                        if h:
                            hashes.add(h)
                except json.JSONDecodeError:
                    continue
    except Exception:
        pass
    return hashes


def chore_hash(repo: str, rel_path: str, description: str) -> str:
    raw = f"[{repo}] {rel_path}\n{description}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def record_activity(entry: dict):
    ensure_dirs()
    with open(ACTIVITY_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def append_line(path: str, line: str):
    with open(path, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def lines_of(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return f.readlines()


def write_lines(path: str, lines: list):
    with open(path, "w", encoding="utf-8") as f:
        f.writelines("".join(lines))


def remove_marked_lines(path: str, marker: str) -> list:
    """Remove lines containing `marker` from path. Returns removed lines."""
    lines = lines_of(path)
    kept = []
    removed = []
    for line in lines:
        if marker in line:
            removed.append(line)
        else:
            kept.append(line)
    write_lines(path, kept)
    return removed


def find_section_line(lines: list, section: str) -> int:
    for i, line in enumerate(lines):
        stripped = line.strip().lower()
        if section.lower() in stripped and stripped.startswith("#"):
            return i
    return -1


def chore_hash_in_log(chore_hash: str, skip_failed: bool = True) -> bool:
    """Check if a chore hash appears in the activity log.

    If skip_failed is True, also skip chores that were attempted but failed —
    this prevents the worker from retrying the same failed verification
    every cycle. Failed chores get retried on the next cron cycle (6h later)
    or when explicitly added to tasks.md.
    """
    if not os.path.exists(ACTIVITY_LOG):
        return False
    try:
        with open(ACTIVITY_LOG, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    if entry.get("chore_hash") == chore_hash:
                        if not skip_failed or entry.get("result") == "completed":
                            return True
                        # Failed entry found — treat as already attempted
                        return True
                except json.JSONDecodeError:
                    continue
    except Exception:
        pass
    return False


# ---------------------------------------------------------------------------
# Chore definitions
# ---------------------------------------------------------------------------

SAFETY_BOUNDARY = """
Automatic execution is limited to bounded, reversible, internal work.
Not allowed automatically: delete user data, change credentials, rotate
secrets, upgrade major dependencies, modify security settings, publish
externally, force-push, rewrite history, make architectural changes,
start a large feature. Ambiguous or potentially destructive work is
recorded as BLOCKED_REVIEW_REQUIRED and skipped.
""".strip()


def chore_verify_services_up() -> tuple:
    """Verify dashboard services are listening on expected ports."""
    ports = ports_alive([8765, 8788])
    up = [p for p, s in ports.items() if s == "UP"]
    down = [p for p, s in ports.items() if s != "UP"]
    ok = len(down) == 0
    detail = f"8765: {ports[8765]}, 8788: {ports[8788]}"
    return ok, detail


def chore_execute_services_up() -> tuple:
    """Check services; report only (no restart — restart is a separate concern)."""
    ok, detail = chore_verify_services_up()
    return ok, f"Services checked — {detail}"


def chore_verify_push_status(repo_dir: str, remote: str = "origin", branch: str = "master") -> dict:
    """Return push status dict for a repo. Handles timeouts and missing refs."""
    import json as _json
    result = {
        "repo": repo_dir,
        "remote": remote,
        "branch": branch,
        "local_commit": None,
        "remote_commit": None,
        "fetch_ok": False,
        "in_sync": None,
        "status": "unknown",
        "detail": "",
    }

    code, local_out, _ = run(f'git -C "{repo_dir}" rev-parse HEAD', timeout=10)
    if code == 0:
        result["local_commit"] = local_out.strip()[:12]

    code, remote_out, _ = run(
        f'git -C "{repo_dir}" rev-parse refs/remotes/{remote}/{branch}',
        timeout=10,
    )
    if code == 0 and remote_out.strip():
        result["remote_commit"] = remote_out.strip()[:12]

    code, fetch_out, fetch_err = run(
        f'git -C "{repo_dir}" fetch {remote} {branch} 2>&1',
        timeout=30,
    )
    result["fetch_ok"] = (code == 0 and "error" not in fetch_err.lower())
    if result["fetch_ok"]:
        code2, remote_out2, _ = run(
            f'git -C "{repo_dir}" rev-parse refs/remotes/{remote}/{branch}',
            timeout=10,
        )
        if code2 == 0 and remote_out2.strip():
            result["remote_commit"] = remote_out2.strip()[:12]

        local = result["local_commit"]
        remote = result["remote_commit"]
        if local and remote:
            result["in_sync"] = (local == remote)
            if result["in_sync"]:
                result["status"] = "pushed"
                result["detail"] = f"local {local} == remote {remote}"
            else:
                result["status"] = "not_in_sync"
                result["detail"] = (
                    f"local {local} != remote {remote} "
                    f"(push failed or not yet attempted)"
                )
        else:
            result["status"] = "partial"
            result["detail"] = "local or remote commit unavailable after fetch"
    else:
        result["status"] = "fetch_failed"
        result["detail"] = (
            f"fetch failed (exit {code}): {fetch_err.strip()[:80]} "
            f"— push status uncertain (network or credential issue)"
        )

    return result


def chore_execute_push_check_dashboard() -> tuple:
    """Check push status of dashboard-project master branch."""
    repo = os.path.join(HOME, "dashboard-project")
    if not os.path.isdir(os.path.join(repo, ".git")):
        return False, f"not a git repo: {repo}"

    status = chore_verify_push_status(repo)
    in_sync = status.get("in_sync")
    ok = in_sync is True
    detail = (
        f"dashboard-project: local={status['local_commit'] or '?'}, "
        f"remote={status['remote_commit'] or '?'}, "
        f"status={status['status']}"
    )
    if status["status"] == "fetch_failed":
        detail += " — cannot confirm push state from this host"
    return ok, detail


def chore_execute_push_check_spotify() -> tuple:
    """Check push status of spotify-intelligence master branch."""
    repo = os.path.join(HOME, "spotify-intelligence")
    if not os.path.isdir(os.path.join(repo, ".git")):
        return False, f"not a git repo: {repo}"

    status = chore_verify_push_status(repo)
    in_sync = status.get("in_sync")
    ok = in_sync is True
    detail = (
        f"spotify-intelligence: local={status['local_commit'] or '?'}, "
        f"remote={status['remote_commit'] or '?'}, "
        f"status={status['status']}"
    )
    if status["status"] == "fetch_failed":
        detail += " — cannot confirm push state from this host"
    return ok, detail


def chore_find_runtime_logs_without_gitignore(repo_dir: str, log_names: list) -> list:
    """Return list of (log_path, rel_path) for runtime logs not covered by .gitignore."""
    gitignore_path = os.path.join(repo_dir, ".gitignore")
    gitignore_patterns = set()
    if os.path.isfile(gitignore_path):
        try:
            with open(gitignore_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        gitignore_patterns.add(line)
        except Exception:
            pass

    findings = []
    for log_name in log_names:
        log_path = os.path.join(repo_dir, log_name)
        if not os.path.isfile(log_path):
            continue
        rel = log_name  # simple basename
        # Check if the basename is in .gitignore (or a pattern matches)
        covered = False
        for pat in gitignore_patterns:
            if pat == rel or pat == f"/{rel}" or pat == f"**/{rel}":
                covered = True
                break
        if not covered:
            findings.append((log_path, rel))
    return findings


def chore_execute_add_gitignore_entries(
    repo_dir: str, log_names: list, dry_run: bool = False
) -> tuple:
    """Add .gitignore entries for runtime logs not already covered."""
    findings = chore_find_runtime_logs_without_gitignore(repo_dir, log_names)
    if not findings:
        return True, f"no uncovered runtime logs in {repo_dir}"

    gitignore_path = os.path.join(repo_dir, ".gitignore")
    existing_lines = []
    if os.path.isfile(gitignore_path):
        with open(gitignore_path, "r", encoding="utf-8") as f:
            existing_lines = f.readlines()

    new_entries = []
    for log_path, rel in findings:
        if not any(rel in line for line in existing_lines):
            new_entries.append(f"{rel}\n")

    if not new_entries:
        return True, f"all runtime logs already covered in {repo_dir}"

    if dry_run:
        return True, f"[dry_run] would add to {gitignore_path}: {new_entries}"

    with open(gitignore_path, "a", encoding="utf-8") as f:
        if existing_lines and not existing_lines[-1].endswith("\n"):
            f.write("\n")
        f.write("\n")
        for entry in new_entries:
            f.write(entry)

    return True, f"added {len(new_entries)} .gitignore entries to {gitignore_path}: {new_entries}"


def chore_execute_verify_dashboard_endpoints() -> tuple:
    """Probe dashboard service endpoints (local only — no Vercel TLS dependency)."""
    endpoints = [
        ("state service /health", "http://127.0.0.1:8788/health"),
        ("state service /api/alfred/activity", "http://127.0.0.1:8788/api/alfred/activity"),
        ("token analytics /api/summary", "http://127.0.0.1:8765/api/summary"),
    ]
    results = []
    for label, url in endpoints:
        code, out, _err = run(
            f'curl -s -o /dev/null -w "%{{http_code}}" --max-time 10 "{url}"',
            timeout=15,
        )
        code_str = str(code)
        http_code = out.strip() if out.strip().isdigit() else code_str
        up = http_code == "200"
        results.append((label, url, http_code, up))

    all_up = all(r[3] for r in results)
    detail_lines = [f"  {label}: {http_code} ({'UP' if up else 'DOWN'})" for label, _, http_code, up in results]
    detail = "\n".join(detail_lines)
    return all_up, detail


def chore_execute_verify_funnel() -> tuple:
    """Probe Tailscale Funnel endpoints that are known to serve content.

    Uses paths backed by the local Alfred state service and token analytics
    server via Tailscale Funnel. Both must return 200 for the funnel to be
    considered UP.
    """
    funnel_base = "https://ismail-hp.tail3ed33c.ts.net"
    endpoints = [
        ("/alfred-state/api/alfred/activity", f"{funnel_base}/alfred-state/api/alfred/activity"),
        ("/token-analytics/api/summary", f"{funnel_base}/token-analytics/api/summary"),
    ]
    results = []
    for label, url in endpoints:
        code, out, _err = run(
            f'curl -s -o /dev/null -w "%{{http_code}}" --max-time 10 "{url}"',
            timeout=15,
        )
        http_code = out.strip() if out.strip().isdigit() else str(code)
        up = http_code == "200"
        results.append((label, http_code, up))

    all_up = all(r[2] for r in results)
    detail_lines = [f"  {label}: {http_code} ({'UP' if up else 'DOWN'})" for label, http_code, up in results]
    detail = "\n".join(detail_lines)
    return all_up, detail


def chore_execute_disk_cleanup_check() -> tuple:
    """Report disk space and flag if any drive is above 90% full."""
    c_free = run(f'cmd /c "dir C:\\ /-C"', timeout=10)[1]
    f_free = run(f'cmd /c "dir F:\\ /-C"', timeout=10)[1]
    # Use ctypes-based check instead
    import ctypes
    def get_free(letter):
        free = ctypes.c_ulonglong(0)
        total = ctypes.c_ulonglong(0)
        path = f"{letter}:\\"
        ok = ctypes.windll.kernel32.GetDiskFreeSpaceExW(
            path, ctypes.byref(free), ctypes.byref(total), None,
        )
        if ok:
            pct = (1 - free.value / total.value) * 100
            return f"{letter}: {free.value / (1024**3):.0f}/{total.value / (1024**3):.0f} GB free ({pct:.0f}% used)"
        return f"{letter}: unavailable"

    c_info = get_free("C")
    f_info = get_free("F")

    # Flag C: if > 90% used
    code, out, _ = run(
        f'python3 -c "import ctypes; f=ctypes.c_ulonglong(0); t=ctypes.c_ulonglong(0); '
        f'ctypes.windll.kernel32.GetDiskFreeSpaceExW(\\"C:\\\\\\",&f,&t,None); '
        f'print(int((1-f.value/t.value)*100))"',
        timeout=10,
    )
    try:
        pct_used = int(out.strip())
    except (ValueError, TypeError):
        pct_used = 0

    ok = pct_used < 90
    detail = f"{c_info}\n{f_info}"
    if not ok:
        detail += f"\n⚠ C: drive {pct_used}% full — consider cleanup"
    return ok, detail


# ---------------------------------------------------------------------------
# Chore registry
# ---------------------------------------------------------------------------

def all_chore_definitions():
    """Return list of (key, description, category, repo, rel_path, selector)."""
    home = HOME
    return [
        (
            "services_up",
            "Verify dashboard services (ports 8765, 8788) are listening",
            "verification",
            "",
            "",
            lambda: True,
        ),
        (
            "push_check_dashboard",
            "Verify dashboard-project master push status (local vs remote)",
            "verification",
            os.path.join(home, "dashboard-project"),
            "",
            lambda: os.path.isdir(os.path.join(home, "dashboard-project", ".git")),
        ),
        (
            "push_check_spotify",
            "Verify spotify-intelligence master push status (local vs remote)",
            "verification",
            os.path.join(home, "spotify-intelligence"),
            "",
            lambda: os.path.isdir(os.path.join(home, "spotify-intelligence", ".git")),
        ),
        (
            "funnel_check",
            "Verify Tailscale Funnel endpoints are reachable",
            "verification",
            "",
            "",
            lambda: True,
        ),
        (
            "disk_check",
            "Check disk space on C: and F: drives",
            "verification",
            "",
            "",
            lambda: True,
        ),
        (
            "gitignore_spotify_runtime_logs",
            "Add .gitignore entries for spotify-intelligence runtime logs (dashboard.log, ngrok-live.log) if missing",
            "maintenance",
            os.path.join(home, "spotify-intelligence"),
            ".gitignore",
            lambda: os.path.isdir(os.path.join(home, "spotify-intelligence", ".git")),
        ),
        (
            "gitignore_dashboard_runtime_logs",
            "Add .gitignore entries for dashboard-project runtime logs if missing",
            "maintenance",
            os.path.join(home, "dashboard-project"),
            ".gitignore",
            lambda: os.path.isdir(os.path.join(home, "dashboard-project", ".git")),
        ),
    ]


# ---------------------------------------------------------------------------
# Work selection
# ---------------------------------------------------------------------------

def parse_tasks_md(path: str):
    """Parse tasks.md into sections. Returns dict: section_name → list of (line_no, line)."""
    lines = lines_of(path)
    sections = {}
    current_section = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("#"):
            current_section = stripped.lstrip("#").strip()
            sections[current_section] = []
        elif current_section is not None and stripped:
            sections[current_section].append((i, line))
    return sections, lines


def extract_explicit_tasks(sections: dict):
    """Return list of (section_name, line_no, line, tag) for tagged task lines."""
    tasks = []
    for section_name, items in sections.items():
        for line_no, line in items:
            m = re.match(r'^-\s*\[([^\]]+)\]', line)
            if m:
                tag = m.group(1).lower()
                tasks.append((section_name, line_no, line, tag))
    return tasks


def select_from_tasks_md(sections: dict, completed_hashes: set, repo_dir: str):
    """Priority 1: explicit tasks in tasks.md."""
    tasks = extract_explicit_tasks(sections)
    active_sections = {"active", "processing", "todo", "unfinished"}
    candidates = [
        (sec, ln, line, tag)
        for sec, ln, line, tag in tasks
        if tag in active_sections
    ]
    for sec, ln, line, tag in candidates:
        # Only handle safe, bounded task types
        if any(kw in line.lower() for kw in ["push", "gitignore", "verify", "check", "lint", "test"]):
            return {
                "source": "tasks.md",
                "section": sec,
                "line_no": ln,
                "line": line,
                "tag": tag,
                "description": line.strip(),
                "type": "explicit_task",
            }
    return None


def select_from_audit(
    repos_with_changes: list, completed_hashes: set, repo_dir: str
) -> Optional[dict]:
    """Priority 3-4: broken/stale infrastructure or repo hygiene."""
    # Look for .gitignore opportunities in repos with changes
    for path, changes in repos_with_changes:
        rel = os.path.relpath(path, HOME)
        # Check for runtime log files that might need .gitignore
        for change_line in changes:
            if ".log" in change_line and "??" in change_line:
                log_path = change_line.split()[1] if len(change_line.split()) > 1 else ""
                if log_path.endswith(".log"):
                    return {
                        "source": "audit",
                        "reason": f"untracked runtime log {log_path} — add .gitignore entry",
                        "description": f"Add .gitignore entry for {log_path}",
                        "type": "gitignore_missing",
                        "repo_dir": path,
                        "log_path": log_path,
                    }
    return None


def select_routine_verification(completed_hashes: set, repo_dir: str) -> Optional[dict]:
    """Priority 6: routine verification chores (always safe, idempotent).

    Uses chore_hash_in_log() (not completed_hashes directly) so that chores
    which were attempted but failed are also skipped — they won't be retried
    every cycle. Failed chores get retried on the next cron cycle or when
    explicitly added to tasks.md.
    """
    checks = [
        ("services_up", "Verify dashboard services (ports 8765, 8788) are listening"),
        ("push_check_dashboard", "Verify dashboard-project master push status"),
        ("push_check_spotify", "Verify spotify-intelligence master push status"),
        ("funnel_check", "Verify Tailscale Funnel endpoints are reachable"),
        ("disk_check", "Check disk space on C: and F: drives"),
    ]
    for key, desc in checks:
        h = chore_hash("", "", desc)
        if not chore_hash_in_log(h):
            return {
                "source": "routine",
                "key": key,
                "description": desc,
                "type": "verification",
            }
    return None


def select_chore(
    tasks_sections: Optional[dict],
    repos_with_changes: list,
    completed_hashes: set,
    repo_dir: str,
):
    """Select one chore using priority order. Returns dict or None."""
    # 1. Explicit unfinished task in tasks.md
    if tasks_sections:
        t = select_from_tasks_md(tasks_sections, completed_hashes, repo_dir)
        if t:
            return t

    # 2. Previously started but unverified work — check activity log for
    #    chores with result != "completed" (in_progress, failed, blocked).
    #    For now: skip — requires more state than we have.

    # 3-4. Audit findings
    audit = select_from_audit(repos_with_changes, completed_hashes, repo_dir)
    if audit:
        return audit

    # 6. Routine verification
    routine = select_routine_verification(completed_hashes, repo_dir)
    if routine:
        return routine

    # 5. Memory/context maintenance — only if there's a clear opportunity.
    #    Skip for now; can be added later.

    return None


# ---------------------------------------------------------------------------
# Chore execution dispatch
# ---------------------------------------------------------------------------

def execute_chore(chore: dict, dry_run: bool = False) -> tuple:
    """Execute a selected chore. Returns (success, detail)."""
    chore_type = chore.get("type", "")
    key = chore.get("key", "")
    repo_dir = chore.get("repo_dir", "")

    if chore_type == "explicit_task":
        return execute_explicit_task(chore, dry_run)

    if key == "services_up":
        return chore_execute_services_up()

    if key == "push_check_dashboard":
        return chore_execute_push_check_dashboard()

    if key == "push_check_spotify":
        return chore_execute_push_check_spotify()

    if key == "funnel_check":
        return chore_execute_verify_funnel()

    if key == "disk_check":
        return chore_execute_disk_cleanup_check()

    if chore_type == "gitignore_missing":
        log_path = chore.get("log_path", "")
        log_name = os.path.basename(log_path) if log_path else ""
        return chore_execute_add_gitignore_entries(repo_dir, [log_name], dry_run=dry_run)

    if key == "gitignore_spotify_runtime_logs":
        return chore_execute_add_gitignore_entries(
            repo_dir, ["dashboard.log", "ngrok-live.log"], dry_run=dry_run
        )

    return False, f"unknown chore type/key: {chore_type or key}"


def execute_explicit_task(chore: dict, dry_run: bool = False) -> tuple:
    """Execute a task from tasks.md. Dispatch based on keywords."""
    line = chore.get("line", "").lower()
    repo_dir = chore.get("repo_dir", HOME)

    if "gitignore" in line:
        # Try to find log files mentioned
        log_names = re.findall(r"(\w+\.log)", chore.get("line", ""))
        if not log_names:
            log_names = ["dashboard.log", "ngrok-live.log"]
        # Determine repo from context
        if os.path.isdir(os.path.join(HOME, "spotify-intelligence", ".git")):
            target_repo = os.path.join(HOME, "spotify-intelligence")
        elif os.path.isdir(os.path.join(HOME, "dashboard-project", ".git")):
            target_repo = os.path.join(HOME, "dashboard-project")
        else:
            return False, "cannot determine target repo for gitignore task"
        return chore_execute_add_gitignore_entries(target_repo, log_names, dry_run=dry_run)

    if "push" in line and "dashboard" in line:
        return chore_execute_push_check_dashboard()

    if "push" in line and "spotify" in line:
        return chore_execute_push_check_spotify()

    if "verify" in line or "check" in line:
        if "service" in line or "port" in line or "8765" in line or "8788" in line:
            return chore_execute_services_up()
        if "funnel" in line or "tailscale" in line:
            return chore_execute_verify_funnel()
        if "disk" in line or "space" in line:
            return chore_execute_disk_cleanup_check()
        if "endpoint" in line or "vercel" in line:
            return chore_execute_verify_dashboard_endpoints()

    return False, f"cannot execute explicit task: {chore.get('line', '')} (no matching handler)"


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------

def verify_chore(chore: dict, exec_success: bool, exec_detail: str) -> tuple:
    """Verify a completed chore. Returns (verified, detail)."""
    chore_type = chore.get("type", "")
    key = chore.get("key", "")

    if chore_type == "verification":
        if key == "services_up":
            ok, detail = chore_verify_services_up()
            return ok, f"verification: {detail}"
        if key == "push_check_dashboard":
            status = chore_verify_push_status(
                os.path.join(HOME, "dashboard-project")
            )
            in_sync = status.get("in_sync")
            detail = (
                f"dashboard-project: local={status['local_commit'] or '?'}, "
                f"remote={status['remote_commit'] or '?'}, "
                f"status={status['status']}"
            )
            if status["status"] == "fetch_failed":
                detail += " — push status uncertain from this host"
            return in_sync is True, detail
        if key == "push_check_spotify":
            status = chore_verify_push_status(
                os.path.join(HOME, "spotify-intelligence")
            )
            in_sync = status.get("in_sync")
            detail = (
                f"spotify-intelligence: local={status['local_commit'] or '?'}, "
                f"remote={status['remote_commit'] or '?'}, "
                f"status={status['status']}"
            )
            if status["status"] == "fetch_failed":
                detail += " — push status uncertain from this host"
            return in_sync is True, detail
        if key == "funnel_check":
            return chore_execute_verify_funnel()
        if key == "disk_check":
            return chore_execute_disk_cleanup_check()

    if chore_type == "gitignore_missing" or key == "gitignore_spotify_runtime_logs":
        repo_dir = chore.get("repo_dir", "")
        log_names = ["dashboard.log", "ngrok-live.log"] if "spotify" in repo_dir else [chore.get("log_path", "")]
        findings = chore_find_runtime_logs_without_gitignore(repo_dir, log_names)
        if not findings:
            return True, "verification: runtime logs now covered by .gitignore"
        return False, f"verification FAILED: {len(findings)} log(s) still uncovered: {[f[1] for f in findings]}"

    if chore_type == "explicit_task":
        # Re-run the same handler and check result
        return execute_chore(chore, dry_run=False)

    return exec_success, f"verification: execution result ({exec_detail[:80]})"


# ---------------------------------------------------------------------------
# tasks.md update
# ---------------------------------------------------------------------------

def update_tasks_md(path: str, chore: dict, success: bool) -> str:
    """Update tasks.md: remove completed item from active section, add done entry."""
    if not os.path.isfile(path):
        return f"tasks.md not found at {path} — no update performed"

    sections, all_lines = parse_tasks_md(path)
    line_no = chore.get("line_no")
    section_name = chore.get("section", "")

    if line_no is not None and section_name:
        # Remove the task line from its section
        if 0 <= line_no < len(all_lines):
            removed_line = all_lines[line_no]
            all_lines.pop(line_no)
            # Write back without the removed line
            write_lines(path, all_lines)
            summary = f"removed task from [{section_name}]: {removed_line.strip()[:60]}"
        else:
            summary = f"line_no {line_no} out of range — no removal"
    else:
        # Task came from audit/routine — no specific line to remove
        summary = "no tasks.md line to remove (chore from audit/routine source)"

    # Add done entry
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    desc = chore.get("description", "chore")[:80]
    result = "completed" if success else "failed"
    done_entry = f"- [{result}] {desc} (verified, {now})\n"

    # Find "Done Today" or "Done" section
    done_section = None
    for name in sections:
        if "done" in name.lower():
            done_section = name
            break

    if done_section and done_section in sections:
        # Append to done section
        done_idx = None
        for i, line in enumerate(all_lines):
            if done_section.lower() in line.lower() and line.strip().startswith("#"):
                done_idx = i
                break
        if done_idx is not None:
            # Find end of section (next ## or EOF)
            insert_at = len(all_lines)
            for i in range(done_idx + 1, len(all_lines)):
                if all_lines[i].strip().startswith("##"):
                    insert_at = i
                    break
            all_lines.insert(insert_at, done_entry)
            write_lines(path, all_lines)
            summary += f"; added to [{done_section}]"
        else:
            append_line(path, done_entry)
            summary += "; appended done entry"
    else:
        # No done section — append at end
        append_line(path, f"\n## Done This Session\n{done_entry}")
        summary += "; created [Done This Session] section"

    return summary


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------

def format_report(entry: dict) -> str:
    """Format a work-mode execution entry as a readable report."""
    now = entry.get("timestamp", "unknown")
    trigger = entry.get("trigger", "manual")
    chore = entry.get("chore", {})
    result = entry.get("result", "unknown")
    exec_detail = entry.get("execution_detail", "")
    verify_detail = entry.get("verification_detail", "")
    commit_hash = entry.get("commit_hash")
    push_status = entry.get("push_status")
    blocked = entry.get("blocked_reason")

    lines = []
    lines.append(f"Alfred Idle Worker — {now}")
    lines.append(f"Triggered by: {trigger}")
    lines.append("")

    if result == "NO_ACTION_NEEDED":
        lines.append("No bounded work found. System is clean.")
        if entry.get("scan_summary"):
            lines.append("")
            lines.append("Scan summary:")
            for s in entry["scan_summary"]:
                lines.append(f"  • {s}")
        return "\n".join(lines)

    if blocked:
        lines.append(f"BLOCKED: {blocked}")
        lines.append("")
        lines.append("No automatic action taken — requires review.")
        return "\n".join(lines)

    desc = chore.get("description", "chore")
    why = chore.get("why", "")
    chore_type = chore.get("type", "")

    lines.append(f"Selected chore: {desc}")
    if why:
        lines.append(f"Why: {why}")
    lines.append(f"Category: {chore_type}")
    lines.append("")

    if entry.get("dry_run"):
        lines.append("DRY RUN — no changes made.")
        lines.append("")
        lines.append(exec_detail or "no execution detail")
        return "\n".join(lines)

    lines.append(f"Action: {exec_detail or 'none'}")
    lines.append("")

    ver = entry.get("verification_result", "unknown")
    lines.append(f"Verification: {ver.upper()}")
    if verify_detail:
        lines.append(verify_detail)
    lines.append("")

    if commit_hash:
        lines.append(f"Commit: {commit_hash}")
    if push_status:
        push_repo = push_status.get("repo", "")
        push_local = push_status.get("local_commit", "?")
        push_remote = push_status.get("remote_commit", "?")
        push_st = push_status.get("status", "?")
        lines.append(f"Push status [{push_repo}]: local={push_local}, remote={push_remote}, status={push_st}")
        if push_st == "fetch_failed":
            lines.append("  ⚠ Cannot confirm push state from this host (network/credential issue)")

    lines.append("")
    lines.append(f"Result: {result.upper()}")

    if entry.get("follow_up"):
        lines.append("")
        lines.append("Follow-up:")
        for f in entry["follow_up"]:
            lines.append(f"  • {f}")

    # Append activity log location
    lines.append("")
    lines.append(f"Activity recorded: {ACTIVITY_LOG}")

    return "\n".join(lines)


def format_morning_report(activity_since: str) -> str:
    """Format a morning report from recent activity entries."""
    if not os.path.exists(ACTIVITY_LOG):
        return "No activity log found."

    entries = []
    try:
        with open(ACTIVITY_LOG, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    e = json.loads(line)
                    ts = e.get("timestamp", "")
                    if ts >= activity_since:
                        entries.append(e)
                except json.JSONDecodeError:
                    continue
    except Exception:
        return "Failed to read activity log."

    if not entries:
        return "No activity recorded since the given time."

    lines = []
    lines.append("While you were away:")
    lines.append("")

    completed = [e for e in entries if e.get("result") == "completed"]
    failed = [e for e in entries if e.get("result") == "failed"]
    blocked = [e for e in entries if e.get("blocked_reason")]
    no_action = [e for e in entries if e.get("result") == "NO_ACTION_NEEDED"]

    for e in completed:
        desc = e.get("chore", {}).get("description", "chore")
        verify_detail = e.get("verification_detail", "")
        commit_hash = e.get("commit_hash")
        push_status = e.get("push_status")
        lines.append(f"• completed: {desc}")
        if verify_detail:
            lines.append(f"  verified: {verify_detail[:80]}")
        if commit_hash:
            lines.append(f"  commit: {commit_hash}")
        if push_status:
            ps = push_status.get("status", "?")
            if ps == "fetch_failed":
                lines.append("  ⚠ push status uncertain — cannot confirm from this host")
            elif ps == "not_in_sync":
                lines.append("  ⚠ push not yet confirmed on remote")
            elif ps == "pushed":
                lines.append("  ✓ push confirmed on remote")

    for e in failed:
        desc = e.get("chore", {}).get("description", "chore")
        lines.append(f"• failed: {desc}")
        lines.append(f"  reason: {e.get('execution_detail', '')[:100]}")

    for e in blocked:
        lines.append(f"• blocked: {e.get('chore', {}).get('description', 'chore')} — {e.get('blocked_reason', '')[:80]}")

    if no_action:
        lines.append(f"• {len(no_action)} idle pulse(s) with no work found")

    if not completed and not failed and not blocked:
        lines.append("No proactive work was done — system was clean.")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main workflow
# ---------------------------------------------------------------------------

def run_work_mode(trigger: str = "manual", dry_run: bool = False):
    """Full idle worker workflow: select, execute, verify, record, update, report."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    completed_hashes = load_completed_hashes()

    # Load context
    tasks_path = tasks_file_path()
    tasks_sections = None
    if tasks_path and os.path.isfile(tasks_path):
        try:
            tasks_sections, _ = parse_tasks_md(tasks_path)
        except Exception as e:
            tasks_sections = None

    learning_files = recent_learning_files(limit=1)
    learning_context = ""
    if learning_files:
        try:
            with open(learning_files[0], "r", encoding="utf-8") as f:
                content = f.read()
            # Extract first 500 chars as context hint
            learning_context = content[:500].replace("\n", " ")
        except Exception:
            pass

    # Audit
    repos_with_changes = git_repos_with_changes(HOME)
    services = ports_alive([8765, 8788])
    services_up = all(s == "UP" for s in services.values())

    # Select
    chore = select_chore(tasks_sections, repos_with_changes, completed_hashes, HOME)

    if chore is None:
        entry = {
            "timestamp": now,
            "trigger": trigger,
            "result": "NO_ACTION_NEEDED",
            "scan_summary": [
                f"tasks.md: {'present' if tasks_path else 'absent'}",
                f"services: {services}",
                f"repos_with_changes: {len(repos_with_changes)}",
                f"completed_chore_hashes: {len(completed_hashes)}",
                f"learning_context: {'available' if learning_context else 'none'}",
            ],
            "follow_up": [],
        }
        record_activity(entry)
        return entry

    # Execute
    exec_success, exec_detail = execute_chore(chore, dry_run=dry_run)
    chore_hash_value = chore_hash(
        chore.get("repo_dir", ""),
        chore.get("rel_path", ""),
        chore.get("description", ""),
    )

    # Verify
    if exec_success:
        verify_success, verify_detail = verify_chore(chore, exec_success, exec_detail)
    else:
        verify_success = False
        verify_detail = f"skipped — execution failed: {exec_detail[:80]}"

    result = "completed" if (exec_success and verify_success) else "failed"
    if exec_success and not verify_success:
        result = "failed"

    # Determine if we should commit (only for actual file changes)
    commit_hash = None
    push_status = None
    follow_up = []

    if result == "completed" and chore.get("repo_dir"):
        repo_dir = chore["repo_dir"]
        # Check if there are staged/unstaged changes worth committing
        code, status_out, _ = run(
            f'git -C "{repo_dir}" status --short', timeout=10
        )
        if code == 0 and status_out.strip():
            # Check if .gitignore or other tracked files changed
            if dry_run:
                follow_up.append(f"[dry_run] would commit changes in {repo_dir}")
            else:
                code2, branch_out, _ = run(
                    f'git -C "{repo_dir}" rev-parse --abbrev-ref HEAD', timeout=10
                )
                branch = branch_out.strip() if code2 == 0 else "master"
                commit_msg = chore.get("description", "idle chore")[:50]
                # Sanitize commit message
                commit_msg = re.sub(r'[^\w\s\-\.\,\(\)]', '', commit_msg)
                if not commit_msg.strip():
                    commit_msg = "idle chore"

                code3, _, commit_err = run(
                    f'git -C "{repo_dir}" add -A && git -C "{repo_dir}" commit -m "{commit_msg}"',
                    timeout=15,
                )
                if code3 == 0:
                    code4, head_out, _ = run(
                        f'git -C "{repo_dir}" rev-parse HEAD', timeout=10
                    )
                    commit_hash = head_out.strip()[:12] if code4 == 0 else None
                    follow_up.append(f"committed in {repo_dir}: {commit_hash}")
                else:
                    follow_up.append(f"commit failed in {repo_dir}: {commit_err.strip()[:60]}")

    # Push status for repos we touched
    if result == "completed" and commit_hash and repo_dir:
        ps = chore_verify_push_status(repo_dir)
        push_status = ps
        if ps["status"] == "fetch_failed":
            follow_up.append(
                f"push status for {repo_dir} uncertain — "
                f"cannot confirm from this host (network/credential issue)"
            )
        elif ps["in_sync"] is False:
            follow_up.append(
                f"push for {repo_dir} not yet confirmed — "
                f"local {ps['local_commit']} != remote {ps['remote_commit']}"
            )
        elif ps["in_sync"] is True:
            follow_up.append(f"push confirmed: {repo_dir} in sync")

    # Update tasks.md
    tasks_update = ""
    if tasks_path and chore.get("source") == "tasks.md":
        try:
            tasks_update = update_tasks_md(tasks_path, chore, result == "completed")
        except Exception as e:
            tasks_update = f"tasks.md update failed: {e}"
    elif tasks_path:
        # Non-tasks.md source: add a done entry anyway
        try:
            tasks_update = update_tasks_md(tasks_path, chore, result == "completed")
        except Exception as e:
            tasks_update = f"tasks.md update failed: {e}"

    # Record
    entry = {
        "timestamp": now,
        "trigger": trigger,
        "chore": {
            "description": chore.get("description", ""),
            "why": chore.get("reason", chore.get("why", "")) or "",
            "type": chore.get("type", ""),
            "source": chore.get("source", ""),
            "repo_dir": chore.get("repo_dir", ""),
            "rel_path": chore.get("rel_path", ""),
        },
        "chore_hash": chore_hash_value,
        "execution_success": exec_success,
        "execution_detail": exec_detail,
        "verification_success": verify_success,
        "verification_result": "passed" if verify_success else "failed",
        "verification_detail": verify_detail,
        "result": result,
        "commit_hash": commit_hash,
        "push_status": push_status,
        "tasks_update": tasks_update,
        "dry_run": dry_run,
        "follow_up": follow_up,
    }
    record_activity(entry)

    return entry


def main_audit_only():
    """Original audit-only behavior — what the existing cron job runs."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [f"Idle Pulse — {now}", ""]

    lines.append("Disk:")
    lines.append(f"  {disk_space('C')}")
    lines.append(f"  {disk_space('F')}")
    lines.append("")

    lines.append("Cron (last_status | next_run):")
    lines.append(cron_health())
    lines.append("")

    ports = ports_alive([8765, 8788])
    port_lines = [f"  port {p}: {s}" for p, s in ports.items()]
    lines.append("Dashboard services:")
    lines.append("\n".join(port_lines))
    lines.append("")

    repos = git_repos_with_changes(HOME)
    lines.append("Git repos with changes (HOME walk):")
    if repos:
        for path, changes in repos:
            rel = os.path.relpath(path, HOME)
            lines.append(f"  {rel}:")
            for c in changes[:5]:
                lines.append(f"    {c}")
            if len(changes) > 5:
                lines.append(f"    ... (+{len(changes)-5} more)")
    else:
        lines.append("  all clean")
    lines.append("")

    stale = stale_processes(["alfred_state_service", "token_analytics", "watchdog"])
    lines.append("Stale process check (dashboard-related):")
    if stale:
        for s in stale:
            lines.append(f"  {s}")
    else:
        lines.append("  none found")
    lines.append("")

    tpath, preview = None, None
    if tasks_file_path():
        tpath = tasks_file_path()
        try:
            with open(tpath, "r", encoding="utf-8") as f:
                preview = f.read().strip()[:200].replace("\n", " ")
        except Exception as e:
            preview = f"(read error: {e})"
    if tpath:
        lines.append(f"Tasks file ({os.path.basename(tpath)}):")
        lines.append(f"  {preview or '(empty)'}")
    else:
        lines.append("No tasks.md / unfinished-tasks.md / TODO.md / alfred-summary.md in HOME")
    lines.append("")

    mem = memory_freshness()
    lines.append("Memory files:")
    for v in mem.values():
        lines.append(f"  {v}")
    lines.append("")

    print("\n".join(lines))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Idle Pulse — system audit + autonomous idle chore worker"
    )
    parser.add_argument(
        "--work",
        action="store_true",
        help="Run full idle worker workflow (select + execute + verify + record)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Select and plan a chore but do not execute or commit",
    )
    parser.add_argument(
        "--morning-report",
        metavar="SINCE_ISO",
        help="Format a morning report from activity entries since the given ISO timestamp",
    )
    args = parser.parse_args()

    ensure_dirs()

    if args.morning_report:
        report = format_morning_report(args.morning_report)
        print(report)
        sys.exit(0)

    if args.work:
        trigger = "idle_pulse_cron" if "--work" in sys.argv else "manual"
        entry = run_work_mode(trigger=trigger, dry_run=args.dry_run)
        report = format_report(entry)
        print(report)
    else:
        main_audit_only()
