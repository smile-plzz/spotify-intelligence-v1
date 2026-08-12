import base64, json, subprocess

def get(path):
    r = subprocess.run(
        ['gh','api',f'repos/smile-plzz/claude-hub/contents/{path}'],
        capture_output=True, text=True)
    if r.returncode:
        print(f'  {path}: gh error {r.returncode} - {r.stderr.strip()[:200]}')
        return None
    try:
        d = json.loads(r.stdout)
    except Exception as e:
        print(f'  {path}: json parse error - {e} - raw: {r.stdout[:200]!r}')
        return None
    if 'content' not in d:
        print(f'  {path}: missing content key, keys={list(d.keys())}')
        return None
    return base64.b64decode(d['content']).decode()

for f in ['setup/machine-profile-mac-workspace.md',
          'setup/machine-profile-homepc.md',
          'setup/workflow-notes.md']:
    content = get(f)
    print(f'========== {f} ==========')
    if content:
        print(content[:2500])
    else:
        print('  (could not read)')
    print()
