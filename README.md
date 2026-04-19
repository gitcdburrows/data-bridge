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
| `/sql/query` | POST | Run a parameterised SQL query against the local DB |
| `/sql/tables` | GET | List tables and views in the local DB |
| `/sql/tables/{table}` | GET | Describe a table's columns |

All HTTP endpoints auto-render an interactive OpenAPI UI at
[`/docs`](http://localhost:8000/docs).

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

Example of the new contract:

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

### Local SQL query

```js
const res = await fetch("http://localhost:8000/sql/query", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    sql: "SELECT ticker, close FROM prices WHERE ticker = :ticker ORDER BY date DESC LIMIT 100",
    params: { ticker: "IBM" },
  }),
});
const { columns, rows, truncated } = await res.json();
// rows is a list of arrays aligned with `columns`
```

Configure the database via `DATABASE_URL` in `.env` — SQLAlchemy URLs, so
any supported driver works (SQLite, Postgres, MySQL, MSSQL, DuckDB, …).
The service is **read-only by default** (`SQL_READ_ONLY=true`), which
blocks `INSERT / UPDATE / DELETE / DDL` and rejects multi-statement
payloads. Flip it to `false` when you actually need to write. Results
are capped at `SQL_MAX_ROWS` and you can request a smaller cap per call
via `max_rows`.

List / describe tables for an explorer sidebar:

```js
await fetch("http://localhost:8000/sql/tables").then(r => r.json());
// → { schema: null, tables: [...], views: [...] }

await fetch("http://localhost:8000/sql/tables/prices").then(r => r.json());
// → { table: "prices", columns: [{name, type, nullable, ...}] }
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
├── utils/dates.py           # YYYYMMDD helpers + bond-date field registry
├── models/schemas.py        # Pydantic request / response models
├── bloomberg/
│   ├── client.py            # Singleton sync blpapi session
│   ├── service.py           # High-level Bloomberg operations
│   └── subscription.py      # Async session + asyncio.Queue bridge
├── db/
│   ├── engine.py            # Lazy SQLAlchemy engine
│   └── service.py           # Query execution + introspection
└── routers/
    ├── reference.py         # POST /reference
    ├── historical.py        # POST /historical
    ├── intraday.py          # POST /intraday/bars
    ├── instruments.py       # POST /instruments/lookup
    ├── stream.py            # WS   /stream
    └── sql.py               # POST /sql/query, GET /sql/tables
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

## Running the tests

```bash
pip install -r requirements-dev.txt
pytest
```

The suite covers the YYYYMMDD helper, request schemas, response
serialisation for every bond-date field in `KNOWN_DATE_FIELDS`, and an
end-to-end check that a non-canonical request date returns HTTP 400. No
Bloomberg Terminal is required — `tests/conftest.py` stubs `blpapi`.
