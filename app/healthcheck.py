import json, sys, urllib.request
try:
    with urllib.request.urlopen('http://127.0.0.1:8787/api/health', timeout=5) as r:
        data=json.loads(r.read().decode('utf-8'))
    sys.exit(0 if data.get('ok') else 1)
except Exception:
    sys.exit(1)
