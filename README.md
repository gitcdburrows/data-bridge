# Universe Studio ↔ Bloomberg Data Bridge

A FastAPI service that bridges the **Universe Studio** JavaScript explorer
to the **Bloomberg Terminal API** (`blpapi`). It exposes a tidy JSON + WebSocket
surface so the browser-side explorer never has to touch `blpapi` directly.

## What you get

| Endpoint | Method | What it does |
| --- | --- | --- |
| `/health` | GET | Liveness + Bloomberg session status |
| `/reference` | POST | `ReferenceDataRequest` — point-in-time fields |
| `/historical` | POST | `HistoricalDataRequest` — end-of-period time series |
| `/intraday/bars` | POST | `IntradayBarRequest` — intraday OHLCV bars |
| `/instruments/lookup` | POST | `//blp/instruments` ticker search |
| `/stream` | WS | Real-time `//blp/mktdata` subscriptions |

All HTTP endpoints auto-render an interactive OpenAPI UI at
[`/docs`](http://localhost:8000/docs).

## Requirements

1. A machine with an **open Bloomberg Terminal** session (`bbcomm` running,
   default port `8194`). The bridge must run where the Terminal runs
   — usually your workstation.
2. Python 3.10+.
3. The Bloomberg Python SDK. It is **not** on PyPI. Install it from
   Bloomberg's package index:

   ```bash
   pip install \
     --index-url=https://blpapi.bloomberg.com/repository/releases/python/simple/ \
     blpapi
   ```

## Install & run

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                 # then edit as needed
python -m app.main                   # or: uvicorn app.main:app --reload
```

By default the server listens on `http://127.0.0.1:8000` and expects the
Terminal on `localhost:8194`. The `CORS_ORIGINS` env var controls which
origins the JS explorer can call from; set it to your Universe Studio dev
URL(s).

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
    start_date: "2024-01-01",
    end_date: "2024-12-31",
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

## Auth

If you set `API_KEY` in `.env`, every HTTP call must send the matching
`X-API-Key` header, and the WebSocket must be opened with
`ws://.../stream?api_key=<key>`. Leave `API_KEY` blank to disable the check
(fine for a workstation-only dev setup).

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

## Project layout

```
app/
├── main.py                  # FastAPI app + lifespan (session start/stop)
├── config.py                # Settings via pydantic-settings / .env
├── security.py              # Optional X-API-Key dependency
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

- Bloomberg's `blpapi` is vendor-shipped, not on PyPI — `pip install -r
  requirements.txt` will only succeed if you also add Bloomberg's index URL
  (see *Requirements*), or install `blpapi` separately.
- `DAPI` terminal-bound entitlements mean this bridge must run on the same
  workstation as the live Bloomberg Terminal session. Hosting it on a
  shared server requires a B-PIPE entitlement instead.
- The bridge intentionally starts the Bloomberg session **lazily** if the
  Terminal isn't reachable yet. `/health` will report
  `bloomberg_connected: false` until the first successful call.
