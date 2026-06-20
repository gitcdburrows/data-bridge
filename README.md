# Universe Studio ↔ Bloomberg Data Bridge

A small desktop app that bridges the **Universe Studio** JavaScript explorer
to the **Bloomberg Terminal API** (`blpapi`). It runs a local FastAPI service
exposing a tidy JSON + WebSocket surface so the browser-side explorer never
has to touch `blpapi` directly.

It ships as a **single self-contained executable with a tray UI** — no Python
environment, no `pip install`, nothing to configure. Double-click it and a
tray icon shows the live status and lets you restart the server.

## What you get

| Endpoint | Method | What it does |
| --- | --- | --- |
| `/reference` | POST | `ReferenceDataRequest` — point-in-time fields |
| `/historical` | POST | `HistoricalDataRequest` — end-of-period time series |
| `/intraday/bars` | POST | `IntradayBarRequest` — intraday OHLCV bars |
| `/instruments/lookup` | POST | `//blp/instruments` ticker search |
| `/stream` | WS | Real-time `//blp/mktdata` subscriptions |

Plus a few meta/control endpoints:

| Endpoint | Method | What it does |
| --- | --- | --- |
| `/` | GET | HTML status dashboard (Bloomberg connection, uptime, restart) |
| `/health` | GET | Liveness + Bloomberg session status (JSON) |
| `/docs` | GET | Interactive OpenAPI UI |
| `/admin/restart` | POST | Ask the supervisor to restart the server (local-only) |

## Run it as an app (no Python needed)

This is the intended way to run the bridge on the workstation that hosts the
Bloomberg Terminal.

1. Get `BloombergBridge.exe` (see **Building the executable** below).
2. Double-click it. A tray icon appears.
   - **Green** — server up, Bloomberg Terminal connected.
   - **Amber** — server up, Terminal not connected yet.
   - **Grey** — starting / restarting.
   - **Red** — server stopped (it auto-retries).
3. Right-click the tray icon for the menu:
   - **Open status page** — the dashboard at `http://127.0.0.1:8000/`.
   - **Open API docs** — the OpenAPI UI.
   - **Restart server** — tears the server down and brings a fresh one up.
   - **Start on login** (Windows) — toggle launching the app automatically at
     logon. This writes a per-user registry entry, so it needs **no admin /
     UAC prompt**; it runs in your session alongside the Terminal.
   - **Quit**.

Under the hood the tray process *supervises* the server as a child process,
so restarts are clean and a crashed server is automatically respawned (with
backoff). Logs are written to `data-bridge.log` next to the executable.

## Date format contract

**Every date field on the wire — request or response — is an 8-digit
`YYYYMMDD` string with no separators.** This is the only format the
Universe Explorer's `plParseDate` (`pipeline/src/parser.js`) guarantees
to accept; anything else can be misinterpreted locale-to-locale.

- **Requests** — `start_date`, `end_date`, and any date-valued field
  override (e.g. `ASOF_DATE`, `SETTLE_DT`, `MATURITY`) must be
  `YYYYMMDD`. Anything else returns **HTTP 400** with a clear
  `"Date fields must be YYYYMMDD strings"` detail. The full set of
  recognised bond-date mnemonics lives in `app/utils/dates.py`
  (`KNOWN_DATE_FIELDS`).
- **Responses** — every Bloomberg `DATE` scalar is emitted as
  `YYYYMMDD`. Known bond-date mnemonics are additionally canonicalised
  at the serialisation boundary even when Bloomberg returns them as
  `DATETIME` or free-form strings. If an upstream value is
  unparseable, the field is emitted as `null` rather than leaking a
  malformed string downstream (the event is logged at WARN).
- **Intraday datetimes** (bar `time`, `start_datetime`, `end_datetime`)
  keep ISO 8601 because the time-of-day component is meaningful.

Example of the contract:

```json
// Historical request
{
  "securities": ["IBM US Equity"],
  "fields": ["PX_LAST"],
  "start_date": "20250101",
  "end_date":   "20250419"
}

// Historical response (excerpt)
{
  "data": [{
    "security": "IBM US Equity",
    "bars": [
      { "date": "20250102", "fields": { "PX_LAST": 220.15 } },
      { "date": "20250103", "fields": { "PX_LAST": 221.40 } }
    ]
  }]
}

// Reference response for a bond (excerpt)
{
  "data": [{
    "security": "XS1234567890 Corp",
    "fields": {
      "PX_LAST":       97.25,
      "MATURITY":      "20320315",
      "ISSUE_DT":      "20220315",
      "FIRST_CPN_DT":  "20220915"
    }
  }]
}
```

## Security model

The bridge is built to run on a single workstation alongside the Bloomberg
Terminal, so it is deliberately simple:

- **No API key / password.** There is no auth layer to configure.
- It binds to **`127.0.0.1`** by default, so only the local machine can reach
  it. Change `APP_HOST` only if you understand the exposure.
- **CORS** restricts which browser origins may call it. The default allows the
  hosted explorer at `https://universe.thesimplereport.com` plus localhost dev
  ports.
- The `/admin/*` control endpoints reject cross-origin browser requests, so a
  remote page can't restart your bridge.

> Note: a page served over **https** (the hosted explorer) calling
> **http://127.0.0.1** is a mixed-content / cross-origin case. Browsers
> special-case `localhost`, so it generally works, but verify it in your
> target browser once deployed.

## Configuration

The app runs with **zero configuration** — every setting has a sensible
default. To override anything, drop a `.env` file next to the executable
(or in the project root when running from source). See `.env.example`:

| Variable | Default | Purpose |
| --- | --- | --- |
| `BLOOMBERG_HOST` | `localhost` | Terminal / bbcomm host |
| `BLOOMBERG_PORT` | `8194` | Terminal / bbcomm port |
| `APP_HOST` | `127.0.0.1` | Local server bind address |
| `APP_PORT` | `8000` | Local server port |
| `CORS_ORIGINS` | hosted explorer + localhost | Allowed browser origins (comma separated) |

## Building the executable

PyInstaller is **not** a cross-compiler — build on the OS you target. For the
production Windows workstation, run on that machine so `blpapi` is installed
and gets bundled into the `.exe`:

```powershell
# Windows (PowerShell), from the repo root:
scripts\build.ps1
# → dist\BloombergBridge.exe
```

```bash
# macOS/Linux (handy for smoke-testing the app build):
scripts/build.sh
# → dist/BloombergBridge
```

Both scripts create a venv, install dev requirements (resolving `blpapi` from
Bloomberg's package index via `--extra-index-url`), and run
`pyinstaller data_bridge.spec`. The spec produces a single windowed binary;
several lazily-imported dependencies (`blpapi`, pystray's backend, uvicorn's
plugins) are declared explicitly in it, and blpapi's native library is bundled
when it's installed on the build machine. The branded icon in
`assets/icon.ico` is embedded into the binary (regenerate it with
`python scripts/make_icon.py`).

### Code signing (optional but recommended)

An unsigned executable triggers a SmartScreen "unknown publisher" warning on
first run. Signing removes it. `scripts/build.ps1` calls `scripts/sign.ps1`,
which **does nothing unless you provide a certificate** — so unsigned builds
still work. Provide one via environment variables (or parameters):

| Variable | Meaning |
| --- | --- |
| `SIGN_PFX_BASE64` | base64 of a `.pfx` (convenient for CI secrets) |
| `SIGN_PFX_PATH` | path to a `.pfx` on disk (alternative to base64) |
| `SIGN_PFX_PASSWORD` | password for the `.pfx` |
| `SIGN_THUMBPRINT` | SHA1 thumbprint of a cert already in the store |
| `SIGN_TIMESTAMP_URL` | RFC3161 timestamp server (defaults to DigiCert) |

```powershell
$env:SIGN_PFX_PATH = "C:\certs\codesign.pfx"
$env:SIGN_PFX_PASSWORD = "•••"
scripts\build.ps1
```

You need a real **code-signing certificate** to make this meaningful — a
standard OV cert, or for the strongest SmartScreen reputation an EV cert. For
CI, prefer a cloud-HSM-backed option that never exposes key material:
**Azure Trusted Signing**, **DigiCert KeyLocker**, or **SignPath** (free for
open source). Point `SIGN_THUMBPRINT` at the cloud-backed cert in those flows.

## Continuous builds (GitHub Actions)

`.github/workflows/build.yml`:

- **`test`** runs the pytest suite on every push / PR (Linux; `blpapi` is
  stubbed, so no Terminal or vendor SDK needed).
- **`build`** runs on **tag pushes (`v*`)** and manual *Run workflow*
  dispatches: it builds the Windows `.exe` (installing `blpapi` from
  Bloomberg's index so it's bundled), signs it if signing secrets are present,
  writes a SHA256, uploads it as an artifact, and — for tags — publishes a
  GitHub **Release** with the `.exe` attached.

To cut a release: `git tag v0.2.0 && git push origin v0.2.0`.

Add signing in CI by setting repo secrets (`SIGN_PFX_BASE64` +
`SIGN_PFX_PASSWORD`, or `SIGN_THUMBPRINT`); without them the build still
produces an unsigned `.exe`.

### Azure Trusted Signing in CI

The workflow has a built-in Azure Trusted Signing path (Microsoft's managed,
cloud-HSM signing — no key material to store, strong SmartScreen reputation).
Turn it on with a repo **variable** and supply the account details; when the
variable isn't `true`, CI uses the signtool/PFX path instead.

- Repo **variable**: `AZURE_TRUSTED_SIGNING = true` to enable, plus
  `AZURE_TS_ENDPOINT` (e.g. `https://eus.codesigning.azure.net/`),
  `AZURE_TS_ACCOUNT`, `AZURE_TS_PROFILE`.
- Repo **secrets** (service principal): `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`,
  `AZURE_CLIENT_SECRET`.

The service principal needs the **Trusted Signing Certificate Profile Signer**
role on the signing account. Pin `azure/trusted-signing-action` in the
workflow to its current release.

## Running from source (development)

Requires **Python 3.10+** and, to actually reach Bloomberg, the vendor
`blpapi` SDK (not on PyPI):

```bash
python -m venv .venv
source .venv/bin/activate                # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pip install --extra-index-url=https://blpapi.bloomberg.com/repository/releases/python/simple/ blpapi

cp .env.example .env                      # optional — defaults are fine

python run.py                             # tray app (supervisor + server)
python run.py --serve                     # just the server, no tray
uvicorn app.main:app --reload             # server with autoreload (dev)
```

By default the server listens on `http://127.0.0.1:8000` and expects the
Terminal on `localhost:8194`.

## Calling it from Universe Studio (JavaScript)

### Reference data

```js
const res = await fetch("http://localhost:8000/reference", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    securities: ["IBM US Equity", "AAPL US Equity"],
    fields: ["PX_LAST", "NAME", "CRNCY"],
  }),
});
const { data } = await res.json();
// data[0].fields.PX_LAST
```

### Historical time series

```js
const res = await fetch("http://localhost:8000/historical", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    securities: ["SPX Index"],
    fields: ["PX_LAST"],
    start_date: "20240101",   // YYYYMMDD — required, see "Date format contract"
    end_date:   "20241231",
    periodicity: "DAILY",
  }),
});
```

### Intraday bars

```js
await fetch("http://localhost:8000/intraday/bars", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    security: "IBM US Equity",
    event_type: "TRADE",
    interval: 5,
    start_datetime: "2025-04-10T13:30:00",
    end_datetime: "2025-04-10T20:00:00",
  }),
});
```

### Real-time stream (WebSocket)

```js
const ws = new WebSocket("ws://localhost:8000/stream");

ws.onopen = () => {
  ws.send(JSON.stringify({
    action: "subscribe",
    securities: ["IBM US Equity", "AAPL US Equity"],
    fields: ["LAST_PRICE", "BID", "ASK"],
  }));
};

ws.onmessage = (evt) => {
  const msg = JSON.parse(evt.data);
  if (msg.type === "data") {
    console.log(msg.security, msg.fields);
  }
};
```

## How the bridge talks to Bloomberg

- `app/bloomberg/client.py` maintains a **single long-lived synchronous
  `blpapi.Session`** per process for request/response traffic. Access is
  serialised through a lock because `blpapi.Session` is not thread-safe.
- `app/bloomberg/service.py` builds `ReferenceDataRequest`,
  `HistoricalDataRequest`, `IntradayBarRequest`, and `instrumentListRequest`
  messages, then walks the response `Element` trees into plain Python
  dicts with `_element_to_py`.
- `app/bloomberg/subscription.py` opens a **second, asynchronous** session
  per WebSocket client and pumps `SubscriptionData` events into an
  `asyncio.Queue` via `loop.call_soon_threadsafe`, so the FastAPI handler
  can `await` them from the event loop.
- HTTP endpoints dispatch the blocking blpapi calls to the FastAPI thread
  pool via `fastapi.concurrency.run_in_threadpool`, keeping the event
  loop responsive.

## How the app is supervised

- `run.py` is the single entry point. With no arguments it launches the tray
  supervisor; with `--serve` it runs the FastAPI server.
- `app/supervisor.py` is the tray app. It spawns the server as a child
  process (`run.py --serve` / the same `.exe --serve` when frozen), polls
  `/health` to drive the icon colour, and offers Restart/Quit.
- A restart (tray menu **or** the dashboard button → `POST /admin/restart`)
  asks uvicorn to exit cleanly with a sentinel code; the supervisor sees it
  and respawns. Unexpected exits are treated as crashes and retried with
  backoff.

## Project layout

```
run.py                       # entry point: tray supervisor / --serve
data_bridge.spec             # PyInstaller build spec
assets/icon.ico              # app icon embedded in the .exe
scripts/build.ps1|build.sh   # one-command executable builds
scripts/sign.ps1             # optional Authenticode signing
scripts/make_icon.py         # regenerate assets/icon.* from app/icon.py
.github/workflows/build.yml  # CI: test + build/sign/release the .exe
app/
├── main.py                  # FastAPI app, dashboard, /health, /admin/restart
├── runner.py                # server ('serve') mode under uvicorn
├── supervisor.py            # tray app that supervises the server child
├── autostart.py             # per-user 'start on login' (no admin)
├── icon.py                  # branded icon (tray + .exe), tinted by status
├── dashboard.py             # self-contained HTML status page
├── logging_config.py        # file logging (survives windowed builds)
├── config.py                # Settings via pydantic-settings / .env
├── utils/dates.py           # YYYYMMDD helpers + bond-date field registry
├── models/schemas.py        # Pydantic request / response models
├── bloomberg/
│   ├── client.py            # Singleton sync blpapi session
│   ├── service.py           # High-level Bloomberg operations
│   └── subscription.py      # Async session + asyncio.Queue bridge
└── routers/
    ├── reference.py         # POST /reference
    ├── historical.py        # POST /historical
    ├── intraday.py          # POST /intraday/bars
    ├── instruments.py       # POST /instruments/lookup
    └── stream.py            # WS   /stream
```

## Notes & gotchas

- Bloomberg's `blpapi` is vendor-shipped, not on PyPI — installing it needs
  Bloomberg's index URL (see *Running from source*). Build the executable on a
  machine that has it so it gets bundled.
- `DAPI` terminal-bound entitlements mean this bridge must run on the same
  workstation as the live Bloomberg Terminal session. Hosting it on a
  shared server requires a B-PIPE entitlement instead.
- The bridge intentionally starts the Bloomberg session **lazily** if the
  Terminal isn't reachable yet. `/health` reports `bloomberg_connected: false`
  (and the tray icon goes amber) until the first successful call.

## Running the tests

```bash
pip install -r requirements-dev.txt
pytest
```

The suite covers the YYYYMMDD helper, request schemas, response
serialisation for every bond-date field in `KNOWN_DATE_FIELDS`, the end-to-end
HTTP 400 on a non-canonical request date, and the app surface (status
dashboard, trimmed `/health`, the local-only admin guard, and that auth and
SQL are gone). No Bloomberg Terminal is required — `tests/conftest.py` stubs
`blpapi`.
