#!/usr/bin/env bash
# Hermes Dashboard watchdog — runs via Hermes cron daemon (MSYS2 bash).
# Probes http://100.82.108.124:9119 via curl. Silent on success; one alert line on failure.
# Designed for no_agent cron delivery: empty stdout on success = silent; alert on failure.
#
# IMPORTANT: the cron daemon spawns bash without /usr/bin on PATH, so use
# absolute paths for MSYS2 utilities.  date lives in /usr/bin, curl in
# /mingw64/bin — use the correct prefix for each.  Use $(...) command
# substitution — bare VAR=cmd syntax breaks when bash parses the args.

export MSYS2_ARG_CONV_EXCL="*"

URL="https://ismail-hp.tail3ed33c.ts.net/alfred-state/api/alfred/activity"
MAX_TIME=10

# MSYS2 utilities: date is /usr/bin/date, curl is /mingw64/bin/curl
UTC_NOW=$(/usr/bin/date -u +"%Y-%m-%d %H:%M:%S UTC")
HTTP_CODE=$(/mingw64/bin/curl -sSL --max-time "$MAX_TIME" -o /dev/null -w "%{http_code}" "$URL" 2>/dev/null) || true

if [ -z "$HTTP_CODE" ] || [ "$HTTP_CODE" = "000" ]; then
  echo "HERMES DASHBOARD DOWN at $UTC_NOW: $URL not reachable (curl connection failed)"
  exit 1
elif [ "$HTTP_CODE" -ge 200 ] && [ "$HTTP_CODE" -lt 400 ]; then
  # Up — silent
  exit 0
else
  echo "HERMES DASHBOARD DOWN at $UTC_NOW: $URL returned HTTP $HTTP_CODE"
  exit 1
fi
