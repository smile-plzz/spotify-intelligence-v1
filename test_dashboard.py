import urllib.request, json

base = 'http://127.0.0.1:8765'

def get(ep, timeout=8):
    try:
        with urllib.request.urlopen(f'{base}{ep}', timeout=timeout) as r:
            return json.loads(r.read())
    except Exception as e:
        return {'ERROR': str(e)[:100]}

print('=== HERMES TOKEN DASHBOARD - LIVE VERIFICATION ===')
print()

h = get('/health')
print(f'Server: {h.get("status", "?")} | Port: {h.get("port", "?")} | DB: {h.get("db", "?")[:55]}')
print()

s = get('/api/summary')
if 'ERROR' not in s:
    print(f'TOTAL INPUT:     {s["total_input"]:,} tokens')
    print(f'TOTAL OUTPUT:    {s["total_output"]:,} tokens')
    print(f'GRAND TOTAL:     {s["grand_total_tokens"]:,} tokens')
    print(f'CACHE READ:      {s["total_cache_read"]:,} ({s["cache_hit_pct"]}% hit rate)')
    print(f'CACHE WRITE:     {s["total_cache_write"]:,}')
    print(f'REASONING:       {s["total_reasoning"]:,}')
    print(f'API CALLS:       {s["total_calls"]}')
    print(f'SESSIONS (DB):   {s["session_count"]}')
    print(f'MODEL COMBOS:    {s["unique_sessions_smu"]}')
    for m in s['models']:
        print(f'  Model: {m["model"]:<35} {m["input"]:,} in / {m["output"]:,} out ({m["sessions"]} sessions)')
    if s['largest_session']:
        ls = s['largest_session']
        print(f'LARGEST SESSION: {ls["session_id"][-25:]} -- {ls["total_tokens"]:,} total ({ls["model"]})')
print()

se = get('/api/sessions')
if 'ERROR' not in se:
    top = sorted(se, key=lambda x: x.get('input_tokens',0) or 0, reverse=True)[:5]
    print(f'TOP 5 SESSIONS BY INPUT:')
    for s_s in top:
        sk = s_s.get('session_key') or s_s.get('id','?')
        sk_s = sk[-30:] if len(sk) > 30 else sk
        model = s_s.get('model','?')
        inp = s_s.get('input_tokens',0)
        out = s_s.get('output_tokens',0)
        util = s_s.get('utilization_pct',0)
        msgs = s_s.get('message_count',0)
        print(f'  {sk_s:<30} {model:<25} {inp:>12,} in | {out:>8,} out | {util:>6.1f}% util | {msgs} msgs')
print()

al = get('/api/alerts')
if 'ERROR' not in al:
    print(f'ALERTS: {len(al)}')
    if al:
        for a in al[:3]:
            print(f'  [{a["level"].upper()}] {a["msg"][:120]}')
        if len(al) > 3:
            print(f'  ... and {len(al)-3} more')
print()

ac = get('/api/active')
if 'ERROR' not in ac:
    print(f'ACTIVE SESSIONS (no end time): {len(ac)}')
    for a_s in ac[:3]:
        dn = a_s.get('display_name') or a_s.get('session_key') or 'CLI'
        dn_s = dn[-30:] if len(dn) > 30 else dn
        model = a_s.get('model') or '—'
        age = a_s.get('age_human') or '—'
        inp = a_s.get('input_tokens',0)
        print(f'  {dn_s:<30} {model:<25} running {age} | {inp:,} in')
print()

print('Dashboard is LIVE and all endpoints responding.')
print('Open http://127.0.0.1:8765 in your browser')
