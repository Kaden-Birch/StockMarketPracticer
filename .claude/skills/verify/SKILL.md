# Verify AIPTP

How to build, launch, and drive this app to verify changes end-to-end.

## Build & launch

```bash
python3 -m venv .venv && .venv/bin/pip install -e "backend[dev]"
cd frontend && npm install && npm run build && cd ..   # server serves frontend/dist
AIPTP_DATA_DIR=/tmp/aiptp-verify .venv/bin/python -m aiptp.main   # port 8420
```

Launch the server with the harness's `run_in_background` (or an equivalent
detached process) — plain `&` children get reaped when the shell exits.
Never `pkill -f aiptp.main` — that pattern can match your own shell/session
command line; use `pkill -f "aiptp[.]main"` at minimum.

`AIPTP_MARKET_PROVIDERS=fake` gives deterministic prices without network.
Default chain is `yahoo,stooq` (keyless, real data; works through the proxy);
`alphavantage` joins the chain when `AIPTP_ALPHAVANTAGE_KEY` is set.

## Flows worth driving

- `GET /api/v1/health` → `{"status":"ok"}`
- Create portfolio → `POST /api/v1/portfolios {"name":..,"starting_balance":"25000"}`
- Market buy real symbol → `POST /api/v1/portfolios/{id}/orders {"symbol":"AAPL","side":"BUY","type":"MARKET","quantity":"10"}` → status FILLED at a real quote
- Non-marketable limit order → status PENDING; cancel via DELETE
- Check invariant: portfolio `total_value` == cash + market value; buys/sells conserve value at flat prices
- `GET /api/v1/marketdata/history/AAPL?range=1M` → real bars
- WebSocket `ws://127.0.0.1:8420/api/v1/ws` → `quotes` event within ~15s (watcher interval) once a position or pending order exists
- Deep-link SPA routes must return 200: `curl -o /dev/null -w "%{http_code}" http://127.0.0.1:8420/companies/AAPL`

## UI screenshots

Playwright: `npm i playwright-core` in scratchpad, launch with
`executablePath: "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"` (the
`/opt/pw-browsers/chromium` dir is empty — use the versioned dir) and
`--no-sandbox`. Theme persists in localStorage key `aiptp-theme`; the toggle
button label is the theme it switches TO.

## Gotchas

- Backend tests: `cd backend && ../.venv/bin/python -m pytest -q` (44+ tests, ~3s).
- Schema changes: no migrations yet (pre-1.0) — delete the data dir for a fresh DB.
- The recurring-purchase job runs every 60s; a plan created without start_at
  executes within a minute (origin AUTOMATION on the transaction).
- Yahoo quote `market_state` is often UNKNOWN (chart-meta endpoint); UI hides it.
- Watcher fires every 15s; wait ≥ one interval for pending-order fills.
