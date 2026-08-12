import base64, json, subprocess

def get(path):
    r = subprocess.run(
        ['gh','api',f'repos/smile-plzz/claude-hub/contents/{path}'],
        capture_output=True, text=True)
    if r.returncode:
        print(f'  {path}: gh error {r.returncode} - {r.stderr.strip()[:200]}')
        print(f'  raw stdout: {r.stdout[:300]!r}')
        return None
    try:
        d = json.loads(r.stdout)
    except Exception as e:
        print(f'  {path}: json error {e} - stdout: {r.stdout[:200]!r}')
        return None
    if 'content' not in d:
        print(f'  {path}: missing content; keys={list(d.keys())}')
        return None
    return base64.b64decode(d['content']).decode()

for f in ['setup/machine-profile-mac-workspace.md',
          'setup/machine-profile-homepc.md',
          'setup/workflow-notes.md']:
    content = get(f)
    print(f'========== {f} ==========')
    if content:
        print(content)
    else:
        print('  (could not read)')
    print()
