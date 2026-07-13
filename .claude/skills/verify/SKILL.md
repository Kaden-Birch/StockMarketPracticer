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

## Server mode / auth

`AIPTP_AUTH=required` enables the login wall: `/auth/status` →
setup_required → `POST /auth/setup {username, password≥8}` sets a cookie
(curl: `-c/-b cookiejar`). All /api/v1 routes except auth/health then need
the cookie; the WS checks it too.

## Docker

`dockerd` may need starting (`nohup dockerd &`). Build needs the sandbox
proxy CA as a secret; run needs it mounted plus host networking to reach the
proxy:

```
docker build --secret id=extra_ca,src=/root/.ccr/ca-bundle.crt -f deploy/Dockerfile -t aiptp/server .
docker run -d --network host -e AIPTP_PORT=8426 \
  -v /root/.ccr/ca-bundle.crt:/etc/aiptp/ca.crt:ro -e SSL_CERT_FILE=/etc/aiptp/ca.crt \
  -e HTTPS_PROXY="$HTTPS_PROXY" aiptp/server
```

## Local AI (M4)

llama-cpp-python is an optional extra (`pip install -e "backend[dev,ai]"`,
source build ~10 min). Smallest real model: `qwen2.5-0.5b-instruct-q4`
(469MB, POST /ai/models/{id}/install downloads from HF through the proxy,
then /load, /benchmark ≈24 tok/s on 4 CPU cores). Analyze takes 1-2 min on
CPU. Tests use FakeRuntime — no model needed. 0.5B output quality is
erratic (placeholder echoes, repetition loops); the pipeline degrades
safely (salvage parse, ungrounded suggestions dropped, no sizing = no
trade), which is what to verify, not suggestion quality.

## Strategies / backtests / what-if (M5)

POST /strategies (entry/exit ASTs use "$SYMBOL" placeholders), then
POST /strategies/{id}/backtest {"range":"2Y"} → 202 with run_id; poll
GET /strategies/backtests/{run_id} until status != RUNNING (a real 2Y/4-symbol
run takes ~10-30s; progress also streams on the WS). What-if:
POST /portfolios/{id}/whatif {"scenario":{"type":"substitute"|"never_sold"|
"adopt_ai"|"monthly_dca", ...}} — note same-day trades produce delta≈0 by
design (scenarios re-date nothing; they need historical transactions to
diverge).

## Gamification (M6)

GET/PATCH /gamify/profile (username/avatar/gamification_enabled),
POST /gamify/events {kind: company_viewed|companies_compared|
analytics_reviewed|backtest_completed|coach_suggestion_read} (server-side
daily caps), POST /gamify/evaluate forces the achievement/challenge cycle
(also runs every 10 min). Per-portfolio: /report-card, /coach, /game.
Opt-out must return awarded:false and evaluate must no-op.

## Modular architecture (M6.11)

Optional features are modules (`aiptp/modules/`) registered by the
ModuleManager at boot via the event bus — the core never imports them. Check
`GET /api/v1/modules` (states RUNNING/DISABLED/FAILED, UI contributions);
`PUT /api/v1/modules/{id}` toggles (applies after restart). Per-portfolio
`preset` (ACADEMY/LEARNING/PROFESSIONAL) gates module endpoints → 409 when the
preset disables a module (e.g. Learning blocks `/report-card` but keeps
`/coach`). Disabled-at-boot module routes return real 404 JSON (SPA fallback
excludes `/api/`). Notifications now flow ONLY through the event bus — no
publisher calls push_notification directly; mid-transaction publishers pass
`session=` to avoid the SQLite self-deadlock. AI runtime via
`AIPTP_AI_RUNTIME=llama|openai|fake`.

## Multiplayer / community (M7)

Current user is a ContextVar set by the auth middleware (`local`/admin in
desktop mode). Access = owner ∪ portfolio members ∪ admin; denials are 404
(never 403 — existence must not leak). Flows: POST /competitions (PRIVATE →
`invite_code` in the create/creator responses only) → /join creates a fresh
game portfolio at the competition's starting balance → /standings.
POST /portfolios/{id}/members {username, role MANAGER|MEMBER|VIEWER};
proposals: POST /portfolios/{id}/proposals (proposer auto-votes yes; a solo
owner auto-executes) → /vote; majority = floor(n/2)+1 of owner+managers+
members. Clubs: POST /clubs {with_portfolio} → join by invite code also adds
PortfolioMember on the club portfolio. Shares: POST /shares/portfolios/{id}
→ GET /api/v1/shared/{token} is auth-exempt and anonymized (no owner/cash);
DELETE revokes → 404. Leaderboards opt-in via PATCH portfolio
{public_on_leaderboard:true}; **cache is 5 min** — call
`aiptp.api.leaderboards.invalidate_cache()` in tests (also cleared on every
app boot). Discord: PUT /discord/config stores webhook/token encrypted;
POST /discord/commands/preview runs the same handlers the gateway bot uses
(the gateway itself needs optional discord.py — not verifiable here).
Multi-user testing: one TestClient per user against the same `app` object
(cookies are per-client); the first /auth/setup account is admin, then
POST /admin/users creates traders. Trigger ASTs are single-key nodes:
`{"price": {"symbol": "$SYMBOL", "op": "<", "value": 90}}`.

## Gotchas

- Backend tests: `cd backend && ../.venv/bin/python -m pytest -q` (44+ tests, ~3s).
- Schema changes: no migrations yet (pre-1.0) — delete the data dir for a fresh DB.
- The recurring-purchase job runs every 60s; a plan created without start_at
  executes within a minute (origin AUTOMATION on the transaction).
- Yahoo quote `market_state` is often UNKNOWN (chart-meta endpoint); UI hides it.
- Watcher fires every 15s; wait ≥ one interval for pending-order fills.
