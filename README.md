# W System uptime

Outside availability probe for W System (wsystem.dev, api.wsystem.dev). Each probe checks the API health endpoint, the website home page and a VAT lookup. A check counts as down if any of the three fails twice in a row, 5 seconds apart. An incident is 2 or more consecutive failed probes.

Two probe sources:

- **Cloudflare Worker `wsystem-uptime-probe`** (source in `timer/`), cron `*/5 * * * *`. This is the 5-minute timer: GitHub Actions skips most `*/5` schedules, so the GitHub job alone ran only twice in its first day. Results: https://wsystem-uptime-probe.wsystem-dev.workers.dev/probes.jsonl, run log `/runs`, 30-day summary `/uptime.json` (read by https://wsystem.dev/status). Archived here in `data/cf_worker_probes.jsonl` whenever the GitHub job runs.
- **GitHub Actions** (`.github/workflows/probe.yml`), schedule `*/5` kept as a best-effort backup from a second network; appends to `data/probes.jsonl`, summary `data/uptime.json`.

The uptime figure counts probes run, not wall-clock time.
