# W System uptime

Outside availability probe for W System (wsystem.dev, api.wsystem.dev). A GitHub Actions job runs every 5 minutes, checks the API health endpoint, the website home page and a VAT lookup, and appends the result to `data/probes.jsonl`. `data/uptime.json` holds the 30-day summary shown on https://wsystem.dev/status.

A check counts as down if any of the three fails twice in a row, 5 seconds apart. An incident is 2 or more consecutive failed probes. GitHub schedules are best-effort, so the figure is by probes run, not wall-clock time.
