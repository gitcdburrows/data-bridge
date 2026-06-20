"""Self-contained HTML status dashboard served at ``/``.

No external assets or network calls — everything is inline so the page
works offline on the workstation running the bridge. It polls ``/health``
and exposes a Restart button wired to ``/admin/restart``.
"""

from __future__ import annotations

DASHBOARD_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Bloomberg Data Bridge</title>
<style>
  :root { color-scheme: light dark; }
  * { box-sizing: border-box; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    margin: 0; min-height: 100vh; display: flex; align-items: center;
    justify-content: center; background: #0f172a; color: #e2e8f0;
  }
  .card {
    background: #1e293b; border: 1px solid #334155; border-radius: 16px;
    padding: 32px 36px; width: min(440px, 92vw);
    box-shadow: 0 20px 50px rgba(0,0,0,.4);
  }
  h1 { font-size: 18px; margin: 0 0 4px; font-weight: 600; }
  .sub { color: #94a3b8; font-size: 13px; margin: 0 0 24px; }
  .row {
    display: flex; align-items: center; justify-content: space-between;
    padding: 12px 0; border-top: 1px solid #334155; font-size: 14px;
  }
  .row .label { color: #94a3b8; }
  .row .value { font-variant-numeric: tabular-nums; font-weight: 500; }
  .dot { display: inline-block; width: 10px; height: 10px; border-radius: 50%;
         margin-right: 8px; vertical-align: middle; background: #64748b; }
  .dot.up { background: #22c55e; box-shadow: 0 0 0 4px rgba(34,197,94,.15); }
  .dot.warn { background: #f59e0b; box-shadow: 0 0 0 4px rgba(245,158,11,.15); }
  .dot.down { background: #ef4444; box-shadow: 0 0 0 4px rgba(239,68,68,.15); }
  .status-line { display: flex; align-items: center; font-size: 15px;
                 font-weight: 600; margin-bottom: 20px; }
  .actions { display: flex; gap: 10px; margin-top: 24px; }
  button, a.btn {
    flex: 1; text-align: center; text-decoration: none; cursor: pointer;
    font: inherit; font-size: 14px; font-weight: 600; padding: 11px 14px;
    border-radius: 10px; border: 1px solid #334155; background: #334155;
    color: #e2e8f0; transition: filter .15s ease;
  }
  button.primary { background: #2563eb; border-color: #2563eb; color: #fff; }
  button:hover, a.btn:hover { filter: brightness(1.12); }
  button:disabled { opacity: .5; cursor: default; filter: none; }
  .toast { margin-top: 16px; font-size: 13px; color: #94a3b8; min-height: 18px; }
</style>
</head>
<body>
  <div class="card">
    <h1>Bloomberg Data Bridge</h1>
    <p class="sub">Universe Studio &harr; Bloomberg Terminal</p>

    <div class="status-line"><span id="dot" class="dot"></span><span id="state">Checking…</span></div>

    <div class="row"><span class="label">Bloomberg Terminal</span><span class="value" id="bbg">—</span></div>
    <div class="row"><span class="label">Version</span><span class="value" id="ver">—</span></div>
    <div class="row"><span class="label">Server uptime</span><span class="value" id="uptime">—</span></div>

    <div class="actions">
      <a class="btn" href="/docs" target="_blank" rel="noopener">API docs</a>
      <button id="restart" class="primary">Restart server</button>
    </div>
    <div class="toast" id="toast"></div>
  </div>

<script>
const $ = (id) => document.getElementById(id);

function fmtUptime(s) {
  if (s == null) return "—";
  s = Math.floor(s);
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
  if (h) return `${h}h ${m}m`;
  if (m) return `${m}m ${sec}s`;
  return `${sec}s`;
}

async function poll() {
  try {
    const r = await fetch("/health", { cache: "no-store" });
    const d = await r.json();
    const bbg = d.bloomberg_connected;
    $("dot").className = "dot " + (bbg ? "up" : "warn");
    $("state").textContent = bbg ? "Running — Bloomberg connected" : "Running — Bloomberg not connected";
    $("bbg").textContent = bbg ? "Connected" : "Not connected";
    $("ver").textContent = d.version ?? "—";
    $("uptime").textContent = fmtUptime(d.uptime_seconds);
  } catch (e) {
    $("dot").className = "dot down";
    $("state").textContent = "Server unreachable";
    $("bbg").textContent = "—";
    $("uptime").textContent = "—";
  }
}

$("restart").addEventListener("click", async () => {
  const btn = $("restart");
  btn.disabled = true;
  $("toast").textContent = "Restarting server…";
  $("dot").className = "dot down";
  $("state").textContent = "Restarting…";
  try { await fetch("/admin/restart", { method: "POST" }); } catch (e) {}
  // Wait for the supervisor to bring the new process up, then resume polling.
  let tries = 0;
  const wait = setInterval(async () => {
    tries++;
    try {
      const r = await fetch("/health", { cache: "no-store" });
      if (r.ok) {
        clearInterval(wait);
        btn.disabled = false;
        $("toast").textContent = "Server restarted.";
        poll();
        setTimeout(() => ($("toast").textContent = ""), 4000);
      }
    } catch (e) { /* still down, keep waiting */ }
    if (tries > 30) { clearInterval(wait); btn.disabled = false; $("toast").textContent = "Still restarting — check the tray icon."; }
  }, 1000);
});

poll();
setInterval(poll, 2000);
</script>
</body>
</html>
"""
