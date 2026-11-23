#!/usr/bin/env python3
"""W System outside uptime probe (stdlib only). Runs from GitHub Actions (Azure), NOT our box/Render/Cloudflare.
Checks (UP only if ALL pass; each retried once after 5 s to avoid counting a single blip):
  api_health  GET https://api.wsystem.dev/health -> 200, JSON ok, <10 s
  site_home   GET https://wsystem.dev/ -> 200, <10 s
  api_keyless GET https://api.wsystem.dev/verify?vat=IE6388047V -> 200 or 429 (429 = up, rate-limited)  [uses 1 free call/run from the runner IP]
Appends one JSON line to data/probes.jsonl. No secrets used."""
import json, time, urllib.request, urllib.error, sys, os
CHECKS = [('api_health', 'https://api.wsystem.dev/health', (200,)),
          ('site_home', 'https://wsystem.dev/', (200,)),
          ('api_verify', 'https://api.wsystem.dev/verify?vat=IE6388047V', (200, 429))]
def once(url, ok):
    t = time.time()
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'wsystem-outside-probe/1.0'}), timeout=10) as r:
            code = r.status; r.read(2048)
    except urllib.error.HTTPError as e:
        code = e.code
    except Exception as e:
        return False, 0, int((time.time() - t) * 1000), type(e).__name__
    ms = int((time.time() - t) * 1000)
    return code in ok and ms < 10000, code, ms, ''
def run():
    res = {}
    for name, url, ok in CHECKS:
        r = once(url, ok)
        if not r[0]:
            time.sleep(5); r = once(url, ok)
        res[name] = {'ok': r[0], 'code': r[1], 'ms': r[2], **({'err': r[3]} if r[3] else {})}
    return {'ts': int(time.time()), 'up': all(v['ok'] for v in res.values()), 'checks': res,
            'src': os.environ.get('GITHUB_RUN_ID', 'local')}
if __name__ == '__main__':
    rec = run(); os.makedirs('data', exist_ok=True)
    open('data/probes.jsonl', 'a').write(json.dumps(rec, separators=(',', ':')) + '\n')
    print(json.dumps(rec))
