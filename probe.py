#!/usr/bin/env python3
"""W System outside uptime probe (stdlib only). Runs from GitHub Actions (Azure), NOT our box/Render/Cloudflare.
Checks (UP only if ALL pass; each retried once after 5 s to avoid counting a single blip):
  api_health  GET https://api.wsystem.dev/health -> 200, JSON ok, <10 s
  site_home   GET https://wsystem.dev/ -> 200, <10 s
  api_verify  GET https://api.wsystem.dev/verify?vat=IE6388047V with X-API-Key from UPTIME_MONITOR_KEY
              -> 200 = up; 402 or 429 = probe_error (never downtime: that is our own monitor key
              being rate-limited or asked to pay, not an API outage). The key is the dedicated
              unmetered internal-uptime key; do not call this endpoint keyless from the runner
              (that burns the free per-IP allowance and used to be scored as downtime).
Appends one JSON line to data/probes.jsonl. The monitor key is read from the environment only; never logged."""
import json, time, urllib.request, urllib.error, sys, os
CHECKS = [('api_health', 'https://api.wsystem.dev/health', (200,), False),
          ('site_home', 'https://wsystem.dev/', (200,), False),
          ('api_verify', 'https://api.wsystem.dev/verify?vat=IE6388047V', (200,), True)]
def once(url, ok, auth):
    t = time.time()
    headers = {'User-Agent': 'wsystem-outside-probe/1.0'}
    if auth:
        headers['X-API-Key'] = auth
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=10) as r:
            code = r.status; r.read(2048)
    except urllib.error.HTTPError as e:
        code = e.code
        try:
            e.read(2048)
        except Exception:
            pass
    except Exception as e:
        return False, 0, int((time.time() - t) * 1000), type(e).__name__, False
    ms = int((time.time() - t) * 1000)
    if code in ok and ms < 10000:
        return True, code, ms, '', False
    if auth is not None and code in (402, 429) and ms < 10000:
        return True, code, ms, '', True
    return False, code, ms, '', False
def run():
    # Only attach the monitor key to the VAT lookup. If it is missing, do not fall back to a
    # keyless /verify (that path can 402 after the free allowance and is not a real outage).
    key = os.environ.get('UPTIME_MONITOR_KEY') or ''
    res = {}
    for name, url, ok, needs_key in CHECKS:
        if needs_key and not key:
            res[name] = {'ok': True, 'code': 0, 'ms': 0, 'probe_error': True, 'err': 'missing_monitor_key'}
            continue
        auth = key if needs_key else None
        r = once(url, ok, auth)
        if not r[0]:
            time.sleep(5); r = once(url, ok, auth)
        rec = {'ok': r[0], 'code': r[1], 'ms': r[2]}
        if r[3]:
            rec['err'] = r[3]
        if r[4]:
            rec['probe_error'] = True
        res[name] = rec
    return {'ts': int(time.time()), 'up': all(v['ok'] for v in res.values()), 'checks': res,
            'src': os.environ.get('GITHUB_RUN_ID', 'local')}
if __name__ == '__main__':
    rec = run(); os.makedirs('data', exist_ok=True)
    open('data/probes.jsonl', 'a').write(json.dumps(rec, separators=(',', ':')) + '\n')
    print(json.dumps(rec))
