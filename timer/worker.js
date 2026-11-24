// W System uptime probe timer (Cloudflare Worker "wsystem-uptime-probe", cron */5, Workers Free plan).
// Why: GitHub Actions skips most */5 schedules, so the GitHub probe alone ran twice in a day.
// Each cron run executes the same checks as github.com/wsystemdev/wsystem-uptime probe.py (one retry after 5 s)
// and stores one row in D1. GitHub Actions keeps probing as a backup from a second network (Azure); the public
// summary merges both sources. No secrets are needed. Public read endpoints: /uptime.json, /probes.jsonl, /runs.
const CHECKS = [["api_health", "https://api.wsystem.dev/health", [200]],
                ["site_home", "https://wsystem.dev/", [200]],
                ["api_verify", "https://api.wsystem.dev/verify?vat=IE6388047V", [200, 429]]];
const GH_RAW = "https://raw.githubusercontent.com/wsystemdev/wsystem-uptime/main/data/probes.jsonl";
const W = 30 * 86400;
const CORS = {"Access-Control-Allow-Origin": "*", "Cache-Control": "public, max-age=60"};

async function once(url, ok) {
  const t = Date.now();
  try {
    const r = await fetch(url, {headers: {"User-Agent": "wsystem-outside-probe/1.0 (cf-worker)"}, signal: AbortSignal.timeout(10000), cf: {cacheTtl: 0}});
    await r.body?.cancel();
    const ms = Date.now() - t;
    return {ok: ok.includes(r.status) && ms < 10000, code: r.status, ms};
  } catch (e) { return {ok: false, code: 0, ms: Date.now() - t, err: (e && e.name) || "Error"}; }
}
async function probe() {
  const checks = {};
  for (const [name, url, ok] of CHECKS) {
    let r = await once(url, ok);
    if (!r.ok) { await new Promise(s => setTimeout(s, 5000)); r = await once(url, ok); }
    checks[name] = r;
  }
  return {ts: Math.floor(Date.now() / 1000), up: Object.values(checks).every(c => c.ok), checks, src: "cf-worker"};
}
function summarize(rows, now) {
  rows = rows.filter(r => r.ts >= now - W).sort((a, b) => a.ts - b.ts);
  const n = rows.length, up = rows.filter(r => r.up).length, days = {}, inc = [];
  let cur = null;
  for (const r of rows) {
    const d = new Date(r.ts * 1000).toISOString().slice(0, 10);
    (days[d] = days[d] || [0, 0])[0]++; if (r.up) days[d][1]++;
    if (!r.up) { cur = cur || {start: r.ts, probes: 0}; cur.probes++; cur.end = r.ts; }
    else if (cur) { if (cur.probes >= 2) inc.push(cur); cur = null; }
  }
  if (cur && cur.probes >= 2) inc.push(cur);
  const lat = rows.filter(r => r.checks?.api_health?.ok).map(r => r.checks.api_health.ms).sort((a, b) => a - b);
  const bySrc = {}; for (const r of rows) bySrc[r.src === "cf-worker" ? "cf-worker" : "github-actions"] = (bySrc[r.src === "cf-worker" ? "cf-worker" : "github-actions"] || 0) + 1;
  const cf = rows.filter(r => r.src === "cf-worker").map(r => r.ts);
  const gaps = cf.slice(1).map((t, i) => t - cf[i]).sort((a, b) => a - b);
  return {generated: now, window_days: 30, probes: n, first_probe: n ? rows[0].ts : null, last_probe: n ? rows[n - 1].ts : null,
    days_of_data: Object.keys(days).length, uptime_pct: n ? Math.round(100000 * up / n) / 1000 : null,
    api_health_p50_ms: lat.length ? lat[Math.floor(lat.length / 2)] : null, api_health_p95_ms: lat.length ? lat[Math.floor(lat.length * 0.95)] : null,
    daily: Object.fromEntries(Object.entries(days).sort().map(([d, v]) => [d, Math.round(10000 * v[1] / v[0]) / 100])),
    incidents: inc.slice(-10), by_source: bySrc,
    cf_worker_interval_s: gaps.length ? {median: gaps[Math.floor(gaps.length / 2)], max: gaps[gaps.length - 1], runs: cf.length} : null,
    cf_first_probe: cf.length ? cf[0] : null,
    method: "outside probe: Cloudflare Worker cron every 5 min (since first cf-worker probe) plus GitHub Actions runs when GitHub schedules them; up = API health + website + VAT lookup all pass (one retry 5 s later); incident = 2+ consecutive failed probes"};
}
async function ghRows() {
  try {
    const r = await fetch(GH_RAW, {signal: AbortSignal.timeout(10000), cf: {cacheTtl: 0}});
    if (!r.ok) return [];
    return (await r.text()).split("\n").filter(Boolean).map(l => { try { return JSON.parse(l); } catch { return null; } })
      .filter(x => x && x.src !== "cf-worker");
  } catch { return []; }
}
async function rebuild(env) {
  const now = Math.floor(Date.now() / 1000);
  const {results} = await env.DB.prepare("SELECT rec FROM probes WHERE ts >= ?").bind(now - W).all();
  const rows = results.map(x => JSON.parse(x.rec)).concat(await ghRows());
  const s = summarize(rows, now);
  await env.DB.prepare("INSERT OR REPLACE INTO summary (id, json) VALUES (1, ?)").bind(JSON.stringify(s)).run();
  return s;
}
export default {
  async scheduled(event, env, ctx) {
    const started = Math.floor(Date.now() / 1000);
    await env.DB.prepare("INSERT INTO runs (ts, cron) VALUES (?, ?)").bind(started, event.cron || "").run();
    const rec = await probe();
    await env.DB.prepare("INSERT INTO probes (ts, up, rec) VALUES (?, ?, ?)").bind(rec.ts, rec.up ? 1 : 0, JSON.stringify(rec)).run();
    await rebuild(env);
    // Optional: also wake the GitHub workflow if a repo-scoped token (Actions: write on wsystemdev/wsystem-uptime only) is set as a secret.
    if (env.GH_DISPATCH_TOKEN) ctx.waitUntil(fetch("https://api.github.com/repos/wsystemdev/wsystem-uptime/actions/workflows/probe.yml/dispatches", {
      method: "POST", body: JSON.stringify({ref: "main"}),
      headers: {Authorization: "Bearer " + env.GH_DISPATCH_TOKEN, Accept: "application/vnd.github+json", "User-Agent": "wsystem-uptime-probe"}}).catch(() => null));
    await env.DB.prepare("DELETE FROM runs WHERE ts < ?").bind(started - 90 * 86400).run();
  },
  async fetch(req, env) {
    const u = new URL(req.url);
    if (u.pathname === "/uptime.json") {
      const row = await env.DB.prepare("SELECT json FROM summary WHERE id = 1").first();
      return new Response(row ? row.json : "{}", {headers: {...CORS, "Content-Type": "application/json"}});
    }
    if (u.pathname === "/probes.jsonl") {
      const since = Number(u.searchParams.get("since") || 0);
      const {results} = await env.DB.prepare("SELECT rec FROM probes WHERE ts >= ? ORDER BY ts").bind(since).all();
      return new Response(results.map(x => x.rec).join("\n") + (results.length ? "\n" : ""), {headers: {...CORS, "Content-Type": "application/x-ndjson"}});
    }
    if (u.pathname === "/runs") {
      const {results} = await env.DB.prepare("SELECT ts, cron FROM runs ORDER BY ts DESC LIMIT 50").all();
      return new Response(JSON.stringify(results), {headers: {...CORS, "Content-Type": "application/json"}});
    }
    return new Response("W System outside uptime probe. Data: /uptime.json, /probes.jsonl, /runs. Source: https://github.com/wsystemdev/wsystem-uptime\n",
      {headers: {...CORS, "Content-Type": "text/plain; charset=utf-8"}});
  },
};
