#!/usr/bin/env python3
"""Copies the Cloudflare Worker probes (https://wsystem-uptime-probe.wsystem-dev.workers.dev/probes.jsonl) into
data/cf_worker_probes.jsonl so this repo keeps a public archive of every probe. Stdlib only, no secrets."""
import json, os, urllib.request
F = 'data/cf_worker_probes.jsonl'
have = set()
if os.path.exists(F):
    have = {json.loads(l)['ts'] for l in open(F) if l.strip()}
since = max(have) + 1 if have else 0
u = f'https://wsystem-uptime-probe.wsystem-dev.workers.dev/probes.jsonl?since={since}'
with urllib.request.urlopen(urllib.request.Request(u, headers={'User-Agent': 'wsystem-uptime-archive/1.0'}), timeout=20) as r:
    new = [l for l in r.read().decode().splitlines() if l.strip() and json.loads(l)['ts'] not in have]
os.makedirs('data', exist_ok=True)
open(F, 'a').writelines(l + '\n' for l in new)
print('archived', len(new))
