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

## Learning ecosystem (M8)

Mentor: POST /mentor/refresh runs the deterministic behavior engine
(observations upsert per (user, code); missing codes → RESOLVED, kept as
the "résumé"); `company_viewed` is RESEARCH XP — only
`coach_suggestion_read` earns education XP (the no_education_activity
observation resolves via that). Narrative needs a loaded model (409
otherwise). Scenarios: POST /scenarios/sessions {scenario_id} (ids:
dotcom_crash, gfc_2008, covid_crash, inflation_cycle, tech_boom) — real
daily bars via `get_history_window(symbol, p1, p2)` (Yahoo period1/period2;
FakeProvider slices its `history_bars` by ts, so tests must seed bars
INSIDE the scenario's real window for every universe symbol + benchmark).
Trade/advance/comparison under /scenarios/sessions/{id}/...; virtual clock
only moves on /advance; scenario portfolios have `scenario_session_id` set
and are excluded from live listings, the watcher, and corporate actions.
Career: POST /career/evaluate persists; new CareerState rows need explicit
rank=0/completed="[]" (column defaults are insert-time). Mandates: PUT
/portfolios/{id}/mandate; technology uses a curated ticker list; rules can
be `pending` (young portfolio) — compliant is then null, not false.
Classroom: assignments with scenario_id create the scenario session at
/assignments/{id}/start; progress dashboard is instructor-only (403).
Module deps: classroom → scenarios (cascade like discord → notifications).

## AI competitors (M9)

POST /tournaments {template: beat_the_market|growth_vs_value|human_vs_ai}
creates a private competition, auto-joins the caller, and adds AI players
(each runs its first decision cycle synchronously — with the real provider
this fetches quotes + history for the profile universe, so it takes a few
seconds). POST /competitions/{id}/ai-players {profile, difficulty,
adaptive} (creator-only, 403 otherwise). Profiles: conservative, growth,
value, dividend, technical, quant, market_timer, beginner, index. AI
portfolios are owned by "ai:<profile>" and excluded from /portfolios; all
AI trades are origin=AI_AUTO. Transparency: GET /ai-players/{id}/decisions
(reason + data_used.scores + confidence + expected_outcome; HOLD is also
recorded). Force a cycle: POST /ai-players/{id}/cycle — the scheduler
cycle (every 5 min) is patience-gated, so a freshly created player skips
it (run_ai_cycle returns 0 acted). Adaptive test recipe: human leads big
(rig fake price up), force a cycle, look for
data_used.adaptive.borrowed_idea. Fake-provider tests must seed prices for
the profile universes (see ALL_SYMBOLS in test_m9_aicomp) and
history_bars for momentum/value/quant methods; flat default bars mean the
market_timer is risk-ON (price == trend). Analysis: GET
/competitions/{id}/analysis works mid-game. Module dep: ai_competitors →
multiplayer. Scenario comparisons now include ai_index/ai_growth/
ai_value/ai_dividend (style series skip universes with <2 matches).

## Knowledge base (M10)

GET /learn/concepts?q=&category= (35 concepts; content in
aiptp/knowledge/content.py — tests validate integrity: 3 levels, valid
related links, quiz answers in range). GET /learn/concepts/{id} records a
view + awards concept_viewed education XP on FIRST view only. Quiz: POST
/learn/concepts/{id}/quiz {answers:[indices]} → pass ≥70; correct answers
+ explanations come back in results. Paths auto-award path_completed XP
once (marker row concept_id="path:<id>"). Learning achievements land BOTH
in /learn/progress and the real gamify engine after /gamify/evaluate
(check via /gamify/profile achievements[].earned_at — there is no
/gamify/achievements endpoint). Suggestions (/learn/suggestions) are
grounded: concentration names the ticker; mentor gaps map via
MENTOR_CONCEPT_MAP; passed-quiz concepts are filtered out. Simulators:
POST /learn/simulate/{compound_growth|diversification|risk_allocation|
market_crash}; market_crash replays the scenario benchmark window via
get_history_window (FakeProvider: seed SPY bars INSIDE the scenario's
real window). Glossary popovers (frontend Term component) read the cached
list — they do NOT record views/XP; only opening the full concept does.

## Gotchas

- Backend tests: `cd backend && ../.venv/bin/python -m pytest -q` (44+ tests, ~3s).
- Schema changes: no migrations yet (pre-1.0) — delete the data dir for a fresh DB.
- The recurring-purchase job runs every 60s; a plan created without start_at
  executes within a minute (origin AUTOMATION on the transaction).
- Yahoo quote `market_state` is often UNKNOWN (chart-meta endpoint); UI hides it.
- Watcher fires every 15s; wait ≥ one interval for pending-order fills.
