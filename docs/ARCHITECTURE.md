# AIPTP Technical Design & Architecture

**Version:** 1.0
**Status:** Proposed
**Companion to:** [PRD.md](PRD.md)

This document translates the AIPTP Product Requirements Document into a concrete
technical design: technology choices, system architecture, data model, and
subsystem designs. Section references like *(PRD §15)* point back to the PRD
requirement being satisfied.

---

## 1. Architectural Overview

AIPTP is built as a **single core application server with two shells**:

```
┌─────────────────────────────────────────────────────────────────┐
│                        Presentation Layer                       │
│  ┌──────────────────────────┐  ┌─────────────────────────────┐  │
│  │  Desktop Shell (Tauri)   │  │  Browser (Server Mode)      │  │
│  │  wraps the same web UI   │  │  multi-user, remote access  │  │
│  └────────────┬─────────────┘  └──────────────┬──────────────┘  │
│               └───────── React + TS UI ───────┘                 │
└───────────────────────────────┬─────────────────────────────────┘
                    REST + WebSocket (JSON)
┌───────────────────────────────┴─────────────────────────────────┐
│                     Core Application Server                     │
│  ┌───────────┐ ┌────────────┐ ┌───────────┐ ┌────────────────┐  │
│  │ Trading & │ │ Automation │ │ Analytics │ │ AI Subsystem   │  │
│  │ Portfolio │ │ Engine     │ │ & Backtest│ │ (local LLMs)   │  │
│  │ Engine    │ │ (24/7)     │ │ Engine    │ │                │  │
│  └─────┬─────┘ └─────┬──────┘ └─────┬─────┘ └───────┬────────┘  │
│        └─────────────┴──────┬───────┴───────────────┘           │
│                    ┌────────┴────────┐                          │
│                    │ Market Data     │                          │
│                    │ Abstraction     │──► Provider adapters     │
│                    │ Layer (MDAL)    │    (Yahoo, Polygon, …)   │
│                    └────────┬────────┘                          │
│                    ┌────────┴────────┐                          │
│                    │ Storage Layer   │──► SQLite / PostgreSQL   │
│                    └─────────────────┘                          │
└─────────────────────────────────────────────────────────────────┘
```

**Key decision: the desktop app and the server are the same program.** In
Desktop Mode *(PRD §4)* the Tauri shell launches the core server as a local
child process bound to `127.0.0.1` and renders the web UI in a native webview.
In Server Mode the identical server binary runs headless (bare metal or Docker)
and users connect with a browser. This satisfies "same codebase on all
platforms" *(PRD §3)*, "scale from consumer PCs to servers without
architectural changes" *(PRD §28)*, and keeps every feature — automation, AI,
analytics — available in both modes with one implementation.

### 1.1 Technology Stack

| Layer | Choice | Rationale |
| --- | --- | --- |
| Core server | **Python 3.12+ / FastAPI** | Best-in-class ecosystem for financial data (pandas, NumPy), analytics, and local AI integration; async-first for hundreds of concurrent price watchers; fast iteration for a large feature surface. |
| Numerical hot paths | NumPy / pandas, optional **CuPy/CUDA** | GPU-accelerated batch analytics and backtests where hardware allows *(PRD §28)*; identical CPU fallback. |
| Local AI runtime | **llama.cpp** (via `llama-cpp-python`) with GGUF models | Runs entirely on user hardware *(PRD §18)*; CPU + CUDA + Metal + Vulkan backends cover every supported platform; quantization levels map directly to the model-profile requirements. |
| Frontend | **React 18 + TypeScript + Vite** | Mature, accessible component ecosystem; one UI serves desktop shell and browser. |
| Charting | **TradingView Lightweight Charts** (price/candles) + **Apache ECharts** (analytics, allocation, comparisons) | Lightweight Charts is purpose-built for financial time series with 60fps zoom/pan; ECharts covers the interactive analytics charts with WebGL rendering *(PRD §13, §28)*. |
| Desktop shell | **Tauri 2** | Native installers for Windows 10/11, macOS (universal binary), and Linux (deb/rpm/AppImage) *(PRD §3, §6)*; ~10× smaller than Electron; the shell only supervises the local server process and hosts the webview. |
| Database | **SQLAlchemy 2 + Alembic** over **SQLite** (desktop) / **PostgreSQL** (server) | One ORM/migration layer, two backends: zero-config single file for desktop, concurrent multi-user for server *(PRD §4, §27)*. |
| Cache / time series | SQLite/Postgres tables with columnar Parquet cold storage for historical bars | Avoids an extra required service; Parquet keeps multi-year OHLCV compact and fast to scan for backtests. |
| Background jobs | **APScheduler** + asyncio task supervisor inside the server process | Automation, price polling, and scheduled trades without external brokers *(PRD §4, §15)*; no Redis/Celery dependency in desktop mode. |
| Packaging | Tauri bundler (desktop) · **Docker + Compose** (server) | *(PRD §5, §6)* |

Rejected alternatives, briefly: **Electron** (bundle size, RAM); **Flutter**
(weaker web-tech charting ecosystem); **Rust core** (stronger runtime
performance but dramatically slower delivery of the analytics/AI surface —
Python + optional native extensions is the pragmatic path, and hot paths can be
ported to Rust extensions later without changing the architecture);
**Ollama as a hard dependency** (we embed llama.cpp directly so installation
stays "download → install → launch" *(PRD §6)*, but an Ollama adapter is a
supported model-runtime plugin).

### 1.2 Module Layout

The server is a modular monolith — one deployable, strictly separated packages
*(PRD §2, §29)*:

```
backend/
  aiptp/
    api/            FastAPI routers (REST + WebSocket), auth middleware
    core/           config, events, plugin registry, scheduling
    marketdata/     MDAL: provider interface, adapters, cache, corporate actions
    portfolio/      portfolios, holdings, transactions, cost-basis accounting
    trading/        order types, order lifecycle, execution simulator
    automation/     rule definitions, trigger evaluation, action dispatch
    ai/             model manager, inference runtime, assistant, recommendations
    analytics/      metrics, risk, comparisons, what-if simulator
    backtest/       strategy definitions, backtest engine, reports
    gamification/   XP, achievements, challenges, streaks
    social/         leaderboards, sharing, read-only links
    notify/         notification channels (desktop, email, webpush-ready)
    reports/        export pipelines (PDF/CSV/XLSX/JSON/Markdown)
    storage/        SQLAlchemy models, repositories, migrations, backups
frontend/           React app
desktop/            Tauri shell
deploy/             Dockerfile, compose.yaml, launcher
```

Modules communicate through an in-process **event bus** (`core.events`):
`PriceUpdated`, `OrderFilled`, `RecommendationCreated`, `RuleTriggered`,
`DividendPaid`, etc. This is what makes gamification, notifications, and audit
logging pluggable rather than woven through business logic, and it is the same
event stream pushed to clients over WebSocket.

---

## 2. Market Data Abstraction Layer (MDAL) *(PRD §10)*

**Non-negotiable invariant: no fabricated data.** Every price, fundamental, and
event in the system carries provenance (provider, retrieval timestamp,
delay class). If data is unavailable, the UI shows "unavailable" — never an
estimate presented as fact.

### 2.1 Provider Interface

```python
class MarketDataProvider(Protocol):
    capabilities: set[Capability]   # QUOTES, HISTORY, FUNDAMENTALS, NEWS, ...
    def get_quote(self, symbols: list[str]) -> list[Quote]: ...
    def get_history(self, symbol: str, interval: Interval,
                    start: datetime, end: datetime) -> list[Bar]: ...
    def get_fundamentals(self, symbol: str) -> Fundamentals | None: ...
    def get_corporate_actions(self, symbol: str) -> list[CorporateAction]: ...
    def get_news(self, symbols: list[str]) -> list[NewsItem]: ...
```

Adapters are plugins *(PRD §29)* registered by capability. A **routing layer**
selects providers per request type with failover, per-provider rate limiting,
and quota tracking. Initial adapters: Yahoo Finance (no key required — default
out-of-box experience), Alpha Vantage, Finnhub, Polygon.io, Tiingo (user
supplies API keys through Settings; keys stored encrypted, §10 below).

### 2.2 Caching & Offline Capability *(PRD §2)*

- **Quote cache:** in-memory, TTL by delay class (real-time vs 15-min delayed).
- **History cache:** Parquet files per symbol/interval, append-only,
  deduplicated; makes charts, analytics, and backtests fully offline-capable
  once data has been fetched.
- **Fundamentals/news cache:** DB tables with `fetched_at` for staleness
  display. The UI always shows data age when offline.

### 2.3 Price Watch Scheduler

A single coalescing poller watches the union of: open-position symbols,
watchlist symbols, symbols referenced by active automation rules and pending
orders. Symbols are polled in batches at provider-appropriate intervals with
priority tiers (pending-order symbols poll fastest). This is the mechanism that
keeps hundreds of securities monitored responsively *(PRD §28)* and feeds the
automation engine 24/7 in server mode *(PRD §4)*.

---

## 3. Data Model *(PRD §8, §9, §11, §17, §27)*

Core entities (simplified; monetary values stored as `NUMERIC`, never floats):

```
User          id, username, password_hash, role, settings, created_at
Portfolio     id, user_id, name, description, currency, starting_balance,
              cash_balance, cost_basis_method (FIFO|LIFO|AVERAGE), notes
Holding       id, portfolio_id, symbol, quantity (NUMERIC — fractional),
              — derived: avg_cost, market_value, unrealized_pnl
Lot           id, holding_id, quantity_remaining, unit_cost, acquired_at
              — lot-level tracking is what makes FIFO/LIFO/Average exact
Order         id, portfolio_id, symbol, side, type, quantity | notional,
              limit_price, stop_price, trail_amount|percent, time_in_force,
              status (PENDING|TRIGGERED|FILLED|CANCELLED|EXPIRED|REJECTED),
              schedule (for DCA/recurring), origin (see below)
Transaction   id, portfolio_id, order_id, symbol, side, quantity, price,
              fees, fx_rate, executed_at, realized_pnl, lots_consumed,
              origin, origin_detail — IMMUTABLE, append-only
Origin        enum: MANUAL | AUTOMATION(rule_id) | AI_ASSISTED(rec_id)
              | AI_AUTO(rec_id) | DIVIDEND_REINVEST | SPLIT_ADJUST
Recommendation id, portfolio_id, model_id, action, symbol, sizing,
              rationale_text, inputs_snapshot (JSON), confidence,
              status (PENDING|APPROVED|REJECTED|EXPIRED|EXECUTED), created_at
AutomationRule id, portfolio_id, name, trigger_ast (JSON), action, params,
              enabled, cooldown, last_fired_at, fire_count
Watchlist / WatchlistItem
Strategy      id, name, rules_ast, universe, created_at
BacktestRun   id, strategy_id, range, params, results (JSON), created_at
Achievement / UserAchievement / Challenge / XpEvent
AuditLog      id, user_id, action, entity, before/after, timestamp
PriceBar / Fundamentals / CorporateAction / NewsItem   (MDAL cache tables)
```

Design notes:

- **`origin` on every order and transaction** is the backbone of the PRD's
  transparency mandate *(PRD §1, §11, §17)*: AI-assisted trades are permanently
  marked at the data layer, so every chart overlay, report, and export can
  distinguish them without heuristics. `Recommendation.inputs_snapshot` freezes
  exactly which market data and portfolio state the model saw *(PRD §16)*.
- **Transactions are append-only**; corrections are compensating entries. This
  gives free audit history *(PRD §27)* and makes the What-If simulator's
  "replay" approach (§7 below) sound.
- **Lot-level accounting** makes FIFO/LIFO/Average cost *(PRD §9)* and partial
  sales exact, including through splits (split adjustments rewrite lot
  quantities via recorded corporate actions, with an audit entry).
- **Multi-currency** *(PRD §8)*: each portfolio has a base currency;
  transactions record the FX rate at execution time from the MDAL.

---

## 4. Trading Engine *(PRD §9)*

The execution simulator fills orders against real market data only:

| Order type | Simulation behavior |
| --- | --- |
| Market | Fills at current quote (last/mid per settings); outside market hours, queues for next-open fill at the opening print. |
| Limit / Stop / Stop-Limit | Held in the pending-order book; the price watcher evaluates trigger conditions on each quote update; fills at limit price or first satisfying quote. |
| Trailing Stop | Watermark (high/low since placement) maintained by the watcher; triggers on configured retracement ($ or %). |
| DCA / Recurring | APScheduler jobs that emit market orders on the configured cadence *(PRD §9)*; run reliably in server mode, and on desktop, missed runs are executed on next launch using the historical price at the scheduled time (flagged as "backfilled" in the transaction). |
| Percentage allocation | Notional order sized as % of portfolio value or cash at execution time. |

Additional behaviors: optional simulated commission/slippage models (default
zero, configurable for realism), mass buy/sell as batched order groups,
one-click rebalance (generates the minimal order set to reach target weights,
shown for confirmation before execution), dividends auto-credited as cash or
reinvested per portfolio setting when the MDAL reports a `CorporateAction`.

All fills emit `OrderFilled` events → transaction written → portfolio
valuation updated → WebSocket push → gamification/notification/audit hooks.

---

## 5. Automation Engine *(PRD §15)*

Rules are stored as a **JSON trigger AST** — a small, safe boolean expression
tree, never `eval`'d code:

```json
{ "all": [
    { "indicator": {"symbol": "AAPL", "name": "RSI", "period": 14, "op": "<", "value": 30} },
    { "any": [
        { "price": {"symbol": "AAPL", "op": "<", "value": 170} },
        { "pct_move": {"symbol": "AAPL", "window": "1d", "op": "<", "value": -3} }
    ]},
    { "cash": {"op": ">", "value": 1000} }
]}
```

Condition types map 1:1 to the PRD trigger list: `price`, `pct_move`,
`indicator` (from the shared indicator library, §6), `earnings_event`,
`dividend_event`, `news_sentiment`, `schedule` (cron), `allocation`, `cash`,
with `all`/`any`/`not` combinators for custom logic. Actions: buy, sell,
partial buy/sell (shares, notional, or % of position), rebalance, notify-only.

Evaluation is **event-driven, not polling**: the engine subscribes to
`PriceUpdated`, `EarningsAnnounced`, etc., and re-evaluates only rules indexed
by the affected symbol/event type. Safety rails: per-rule cooldowns, daily fire
caps, idempotent firing (a rule fires once per trigger transition, not once per
tick while the condition holds), and a full fire log. The same rule AST is
reused by the Strategy Builder (§8) — build once, run live or backtest.

Because the engine lives in the core server and depends only on APScheduler
and the event bus, it runs identically 24/7 in server mode with no user
connected *(PRD §4, §15)*.

---

## 6. Analytics Engine *(PRD §12, §13, §14, §20)*

A shared **indicator/metric library** (vectorized NumPy/pandas, optional CuPy
GPU path selected at runtime) serves four consumers: dashboards, chart
overlays, automation conditions, and backtests — one implementation, no drift.

- **Portfolio metrics:** time-weighted and money-weighted returns, daily P&L,
  allocation by asset/sector/country, dividend income, turnover.
- **Risk metrics:** Sharpe, Sortino, beta (vs configurable benchmark), max
  drawdown, volatility, diversification score (HHI-based across
  sector/geography/position concentration).
- **Records:** best/worst investment, largest gain/loss, win rate, average
  return, average holding period — computed from the immutable transaction log.
- **Technical indicators:** SMA, EMA, RSI, MACD, Bollinger Bands, ATR, VWAP,
  stochastic (initial set); registered through the plugin registry so custom
  indicators are add-ons *(PRD §29)*.
- **Company comparison** *(PRD §14)*: N-symbol normalized price performance
  plus a fundamentals matrix (revenue, earnings, margins, P/E, EPS, debt, cash
  flow, volatility, AI sentiment) sourced strictly from the MDAL.

Heavy computations run in a process pool; results are cached and invalidated by
the event bus, keeping the UI responsive *(PRD §28)*.

### Charting front end *(PRD §11, §12, §13)*

Chart data is served by dedicated endpoints returning downsampled-as-needed
series. All charts share: zoom/pan, tooltips, custom ranges, indicator
overlays, comparison series, PNG/CSV export, full-screen. Event overlays
(buys, sells, AI trades, dividends, splits, earnings, news) are markers with
distinct glyphs; **AI-originated trades use a dedicated marker style and color
token in both themes** *(PRD §11, §17)*. A global filter store (date range,
portfolio, symbol set) can be toggled to synchronize all visible charts
*(PRD §12, §13)*.

---

## 7. What-If Simulator *(PRD §21)*

Implemented as **transaction-log replay against historical MDAL data**, run in
a sandboxed in-memory portfolio — the user's real simulated portfolio is never
touched. Scenario types are transforms over the transaction log:

- *Substitute*: replay with symbol/amount swapped ("$10k in NVDA instead").
- *Suppress*: drop selected sells ("never sold Apple").
- *Adopt recommendations*: replay executing every AI recommendation from the
  recommendation history at its timestamp.
- *Re-schedule*: convert lump sums to periodic purchases ("monthly instead of
  once").

Output is a comparative report (actual vs hypothetical value series, delta,
per-metric comparison) rendered with the standard charting stack and exportable
via the reports pipeline.

---

## 8. Strategy Builder & Backtesting *(PRD §22)*

Strategies = the automation rule AST + a symbol universe + capital/sizing
rules. The backtest engine replays historical bars through the **same
evaluation code paths** as live automation and the same execution simulator as
live trading (bar-close fills, configurable slippage), which is the strongest
guarantee that backtest behavior matches live behavior.

Reports: total return, benchmark comparison, full trade log, win/loss stats,
drawdown analysis, Sharpe/Sortino, and performance segmented by market
condition (bull/bear/sideways regimes detected from the benchmark series).
Backtests run in worker processes with progress streamed over WebSocket; the
GPU path accelerates multi-year, multi-symbol runs when available *(PRD §28)*.

---

## 9. AI Subsystem *(PRD §16, §17, §18, §19)*

### 9.1 Model Runtime

`ai/runtime` wraps llama.cpp behind a `ModelRuntime` interface (so alternative
runtimes — e.g. an Ollama bridge — are plugins). Models are GGUF files in a
managed directory. Hardware detection (CPU features, RAM, GPU/VRAM via
CUDA/Metal/Vulkan probes) drives:

- **Model catalog with profiles** *(PRD §18)*: each entry lists name, version,
  parameters, quantization, disk/RAM/VRAM requirements, estimated speed on the
  detected hardware, and supported features — with a clear
  fits/marginal/doesn't-fit badge.
- **Management** *(PRD §19)*: install (resumable download + checksum), remove,
  update, benchmark (standardized prompt suite measuring tokens/sec and
  latency), compare, and default-model selection globally or per portfolio.
- **Hot switching** *(PRD §18)*: models load/unload at runtime behind the
  interface; requests queue during a swap. Inference runs in a dedicated
  worker process so a busy model can never block the API or automation engine.

### 9.2 Investment Assistant *(PRD §16)*

The assistant is **grounded, tool-using generation — not free-form price
talk**. Pipeline per request:

1. **Context assembly**: deterministic code gathers the relevant real data —
   portfolio composition, positions, computed analytics (§6), MDAL quotes,
   fundamentals, news — into a structured context pack.
2. **Constrained generation**: the model receives the context pack and must
   produce structured output (JSON schema: analysis, suggested actions,
   referenced-data citations, confidence). It is prompted to reference only
   supplied data; numeric claims in the output are validated against the
   context pack before display, and uncited numbers are stripped or flagged.
3. **Persistence**: analysis + `inputs_snapshot` stored as a `Recommendation`,
   making every suggestion permanently explainable ("what data informed this")
   *(PRD §1, §16)*.

Every assistant surface carries the fixed educational disclaimer *(PRD §16)*.

### 9.3 AI-Assisted Trading *(PRD §17)*

Recommendations flow through an approval state machine:

```
PENDING ──user approves──► EXECUTED (origin=AI_ASSISTED)
   │  └──auto-execute ON──► EXECUTED (origin=AI_AUTO)
   ├──user rejects──► REJECTED
   └──TTL elapses──► EXPIRED
```

The review UI shows action, rationale, confidence, and **expected portfolio
impact** (computed deterministically by the analytics engine, not by the LLM:
projected allocation/cash/risk-metric changes). Auto-execution is opt-in per
portfolio and guarded by user-configurable limits (max trade size, max daily
AI trades, symbol allow/deny lists). Origin marking is enforced at the data
layer (§3), so AI trades are permanently distinguishable everywhere.

---

## 10. Security *(PRD §27)*

- **Auth:** Argon2id password hashing; session tokens (HTTP-only cookies for
  browser, OS keychain storage in the desktop shell). Desktop mode defaults to
  a single auto-logged-in local user bound to `127.0.0.1`; server mode requires
  login and supports multiple users.
- **Roles (server mode):** `admin` (users, system settings, providers),
  `trader` (full own-portfolio control), `viewer` (read-only, for shared
  deployments) *(PRD §27)*.
- **Secrets:** provider API keys encrypted at rest (AES-GCM; key from OS
  keychain on desktop, key file or env-provided secret in server/Docker mode).
- **Audit:** `AuditLog` rows for auth events, settings changes, rule
  changes, model installs, and all order activity (which is inherently logged
  via immutable transactions).
- **Backups:** scheduled snapshots (SQLite file copy via backup API / `pg_dump`)
  with retention policy; one-click restore in the setup wizard; Compose volume
  layout keeps data/models/backups on separate mounts.
- **Sharing** *(PRD §24)*: read-only portfolio links are random-token URLs
  scoped to a snapshot-view permission; leaderboards are opt-in and
  pseudonymous by default.

---

## 11. Notifications *(PRD §25)*

`notify/` fans event-bus events out to channel adapters per user preference
matrix (event type × channel): **desktop** (native via Tauri / Web
Notifications in browser), **email** (SMTP settings in server mode), and a
channel interface ready for future mobile push. All notifications are also
persisted to an in-app inbox so nothing is missed between sessions.

---

## 12. Gamification & Community *(PRD §23, §24)*

Implemented entirely as event-bus consumers — zero coupling to trading logic,
and disabling gamification (a single user setting) simply detaches the
consumer *(PRD §23)*. XP sources are aligned with the PRD's anti-churn rule:
learning modules, streaks of portfolio review, diversification milestones,
strategy completion, long-term performance — **never trade counts or
frequency**. Achievements/challenges are declarative definitions evaluated
against events. Leaderboards rank normalized returns over fixed windows,
opt-in, anonymous display names by default.

---

## 13. Reports & Export *(PRD §26)*

A single report pipeline renders typed report models (portfolio summary,
performance, transaction history, AI recommendation history, backtest results)
through per-format writers: CSV/JSON (native), XLSX (openpyxl), Markdown
(templates), PDF (headless-rendered HTML templates sharing the app's chart
components, so PDF charts match the UI). Exporters are plugins *(PRD §29)*.

---

## 14. API Design

- **REST** (`/api/v1/…`): resource-oriented endpoints per module
  (`/portfolios`, `/orders`, `/rules`, `/recommendations`, `/models`,
  `/strategies`, `/backtests`, `/reports`, …). OpenAPI schema auto-generated —
  this same API is the future third-party integration surface *(PRD §30)*.
- **WebSocket** (`/ws`): server → client event stream (quotes for subscribed
  symbols, order fills, rule fires, recommendation created, backtest progress,
  notifications). Client subscribes to topics; the same stream drives desktop
  and browser UIs.
- **Versioning:** URL-versioned; additive changes preferred; breaking changes
  gated to major versions.

---

## 15. Deployment & Packaging *(PRD §4, §5, §6)*

**Desktop:** Tauri bundles → NSIS installer (Windows 10/11), notarized
universal `.dmg` (macOS Intel + Apple Silicon), `.deb` (Ubuntu/Debian), `.rpm`
(Fedora), plus AppImage. First launch runs the setup wizard (data directory,
starting portfolio, optional provider keys, optional AI model download). No
command line at any step *(PRD §6)*. Embedded Python runtime ships inside the
bundle (PyInstaller-style frozen server) so users never install Python.

**Server:** 

```yaml
# deploy/compose.yaml (sketch)
services:
  aiptp:
    image: aiptp/server:latest
    ports: ["8420:8420"]
    volumes:
      - aiptp-data:/data        # DB, settings
      - aiptp-models:/models    # GGUF models
      - aiptp-backups:/backups
    deploy:
      resources:
        reservations:
          devices: [{ driver: nvidia, count: all, capabilities: [gpu] }]
    healthcheck:
      test: ["CMD", "aiptp", "healthcheck"]
  db:            # optional profile: postgres for multi-user
    image: postgres:16
```

A `launcher` script/binary provides one-command deployment (`aiptp up`),
optional auto-update (watchtower-compatible labels), health checks, and backup
scheduling *(PRD §5)*. GPU passthrough via the NVIDIA container toolkit;
CPU-only works everywhere by default.

---

## 16. Frontend Design Notes *(PRD §7)*

- **Navigation:** left rail with the eleven PRD sections (Dashboard, Portfolio,
  Companies, AI Assistant, Strategies, Automation, Watchlists, Analytics,
  Leaderboards, Reports, Settings).
- **Theming:** design tokens with light/dark themes; respects OS preference;
  AI-trade markers, gain/loss colors, and chart palettes defined per theme
  with WCAG AA contrast.
- **Accessibility:** full keyboard navigation and shortcut map (`?` overlay),
  ARIA labeling, reduced-motion support, screen-reader-friendly data tables as
  alternatives to every chart.
- **Responsiveness:** fluid layouts from laptop to multi-monitor; detachable
  chart windows (browser pop-outs / additional Tauri windows) for
  multi-monitor setups.
- **State:** React Query for server state, lightweight store (Zustand) for UI
  state including the global synchronized-filter store.

---

## 17. Testing & Quality Strategy

- **Unit:** cost-basis accounting (lot math is the highest-risk correctness
  area — exhaustive FIFO/LIFO/Average cases incl. splits and fractional
  shares), order trigger logic, rule AST evaluation, metric formulas validated
  against reference implementations.
- **Property-based tests** (Hypothesis) for accounting invariants: cash +
  holdings value is conserved across any transaction sequence; replaying the
  transaction log always reproduces current state.
- **Integration:** MDAL adapters against recorded fixtures (never live calls in
  CI); backtest-vs-live-engine equivalence tests on identical data.
- **E2E:** Playwright flows for the critical paths (setup wizard, buy/sell,
  rule creation → simulated trigger, AI recommendation review).
- **AI evaluation:** golden-set prompts asserting structured-output validity,
  citation coverage, and disclaimer presence — model output is checked
  structurally, not for investment "correctness".

---

## 18. Key Risks & Mitigations

| Risk | Mitigation |
| --- | --- |
| Free market-data providers change/limit APIs | MDAL adapter isolation; multiple bundled adapters; aggressive caching; clear data-age UI. |
| Local LLMs underpowered on low-end hardware | Hardware-aware model recommendations; smallest viable default model; assistant degrades gracefully to deterministic analytics (which never require the LLM). |
| Scope breadth stalls delivery | Phased roadmap (ROADMAP.md) with a usable product at the end of every phase; plugin architecture keeps later features additive. |
| LLM hallucinating market facts | Grounded generation with citation validation (§9.2); numeric claims cross-checked against the context pack. |
| Backtest/live divergence eroding trust | Shared evaluation + execution code paths (§8); equivalence tests in CI. |
