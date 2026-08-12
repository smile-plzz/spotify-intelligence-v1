import base64, json, subprocess

def get(path):
    r = subprocess.run(
        ['gh','api',f'repos/smile-plzz/claude-hub/contents/{path}','--jq','.content'],
        capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(f'gh get {path}: {r.stderr}')
    d = json.loads(r.stdout)
    return base64.b64decode(d).decode()

def put(path, msg, content, sha):
    with open('/tmp/ghp.json','w') as f:
        json.dump({'message':msg,'content':base64.b64encode(content.encode()).decode(),
                   'sha':sha,'branch':'main'}, f)
    r = subprocess.run(['gh','api','-X','PUT',
                        f'repos/smile-plzz/claude-hub/contents/{path}',
                        '--input','/tmp/ghp.json'],
                       capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(f'gh put {path}: {r.stderr}')
    return json.loads(r.stdout).get('content',{}).get('sha','?')

for f in ['setup/machine-profile-mac-workspace.md','setup/machine-profile-homepc.md','setup/workflow-notes.md']:
    try:
        print(f'========== {f} ==========')
        print(get(f)[:2000])
        print()
    except Exception as e:
        print(f'{f}: ERROR {e}')
