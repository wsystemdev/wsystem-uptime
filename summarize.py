#!/usr/bin/env python3
"""data/probes.jsonl -> data/uptime.json (public, read by /status). 30-day window = probes with ts >= now-30d.
uptime_pct = up probes / total probes. Also per-day figures and recent incidents (>=2 consecutive down probes)."""
import json, time, datetime, sys
now = int(time.time()); W = 30 * 86400
rows = [json.loads(l) for l in open('data/probes.jsonl') if l.strip()]
rows = [r for r in rows if r['ts'] >= now - W]
n = len(rows); up = sum(r['up'] for r in rows)
days = {}
for r in rows:
    d = datetime.datetime.fromtimestamp(r['ts'], datetime.timezone.utc).strftime('%Y-%m-%d')
    a = days.setdefault(d, [0, 0]); a[0] += 1; a[1] += r['up']
inc, cur = [], None
for r in rows:
    if not r['up']:
        cur = cur or {'start': r['ts'], 'probes': 0}; cur['probes'] += 1; cur['end'] = r['ts']
    elif cur:
        if cur['probes'] >= 2: inc.append(cur)
        cur = None
if cur and cur['probes'] >= 2: inc.append(cur)
lat = sorted(r['checks']['api_health']['ms'] for r in rows if r['checks']['api_health']['ok'])
out = {'generated': now, 'window_days': 30, 'days_of_data': len(days), 'probes': n,
       'uptime_pct': round(100 * up / n, 3) if n else None,
       'api_health_p50_ms': lat[len(lat)//2] if lat else None, 'api_health_p95_ms': lat[int(len(lat)*0.95)] if lat else None,
       'daily': {d: round(100 * v[1] / v[0], 2) for d, v in sorted(days.items())}, 'incidents': inc[-10:],
       'method': 'external probe every 5 min from GitHub Actions; up = health+site+verify all pass (one retry); incident = 2+ consecutive failed probes'}
json.dump(out, open('data/uptime.json', 'w'), indent=1); print(out['uptime_pct'], n)
