# AI Paper Trading Platform (AIPTP)

A modern, cross-platform paper trading application that combines realistic stock
market simulation, advanced analytics, AI-assisted investing, automation,
portfolio management, and gamification into a single application.

All trading uses **simulated funds and simulated positions only**. AIPTP is
designed for education, experimentation, and portfolio analysis — not for
executing real trades.

## Project Status

**Phase: M9 — AI Investment Competitors & Simulated Opponents (working).**
Nine AI investor profiles — Conservative, Growth, Value, Dividend,
Technical, Quant, Market Timer, an educational Beginner that explains its
own mistakes, and a passive Index Fund — join regular competitions as real
entrants, so human/AI/mixed games share one standings system. Each profile
is a deterministic strategy over real quotes and history with a
personality (risk tolerance, patience, confidence, conviction,
adaptability) scaled by four difficulty levels. Every AI action, including
HOLD, is logged with its decision, reason, the data consulted, confidence,
and expected outcome; every AI trade is permanently marked AI_AUTO.
Adaptive opponents read the live standings, borrow the leader's best idea
when trailing and de-risk when ahead. One-click tournaments (Beat the
Market, Growth vs Value, Human vs AI), a deterministic post-game analysis
(why you won or lost, what worked, what went wrong), and historical
index/growth/value/dividend opponents inside scenario replays complete the
milestone. See [docs/RUNNING.md](docs/RUNNING.md) for Mac/Linux install
with GPU-accelerated local AI.

Previously — **M8 (Advanced Learning Ecosystem & AI Mentor):**
A persistent mentor that actually remembers you: deterministic behavioral
analysis over your real trading history (selling winners too early, panic
sells, missing international exposure, concentration, cash drag, knowledge
gaps from the XP trail) with per-insight evidence, durable memory
(repeated habits count up, fixed ones move to a progress résumé), an
investment-style profile, and an optional LLM-narrated mentor note that
only retells the verified findings. Historical scenarios replay real
market history — the dot-com crash, 2008, COVID, the inflation cycle, the
2016-19 tech boom — from genuine daily closes with a forward-only virtual
clock (no future knowledge), trading through the normal order engine, and
comparison charts against the market, three transparent deterministic AI
strategies, and other players. Career mode adds the Intern-to-Institutional
rank ladder with objectives computed from real platform state, portfolio
mandates (retirement/growth/dividend/technology) with rule-by-rule measured
compliance, and advanced challenges. Classroom mode gives instructors
classrooms, invite codes, scenario/mandate assignments, and a live progress
dashboard. Four new optional modules: extended `ai_mentor`, `scenarios`,
`career`, and `classroom` (which cascade-disables with scenarios).

Previously — **M7 (Multiplayer, Community & External Integrations):**
Multi-user server mode with per-portfolio ownership and membership (owners,
managers, members, viewers), admin-managed accounts, competitions where every
entrant starts a fresh game portfolio at the same balance (scored by return,
risk-adjusted return, or diversification), cooperative portfolios whose trade
proposals execute through the normal order path on a majority vote, investment
clubs with discussion boards, shared club portfolios and member rankings,
six opt-in leaderboard categories, revocable anonymous read-only share links
for portfolios and importable strategies, and a Discord integration
(configured entirely in Settings) with webhook notifications, slash-command
handlers, and automatic role suggestions. All of it ships as three new
optional modules — `multiplayer`, `leaderboards`, and `discord` (which
cascade-disables with `notifications`).

Previously — **M6.11 (Modular Platform Architecture):** The app was
refactored into a small Core Platform (trading, market data, portfolios,
analytics, AI model manager, auth, storage) plus optional feature **modules**
(notifications, automation, gamification, AI mentor, reporting) that register
themselves at startup and communicate only through an event bus. A Module
Manager validates dependencies, isolates failures (a crashing module never
takes down the app), and cascades disables. Every portfolio has an
**experience preset** (Academy/Learning/Professional) that gates which modules
act on it, and the UI assembles its navigation and tabs from the running-module
set. AI runtimes (llama.cpp / OpenAI-compatible / Ollama) and notification
channels (Discord/Slack/webhook) are pluggable behind one interface each. Adding
a feature now means adding a module, not editing the core. See
[docs/MODULES.md](docs/MODULES.md).

Previously — **M6 (Gamification, Progression & Learning):** A permanent
investor profile with categorized XP (education, research, portfolio,
challenges — never trading volume), levels and a cosmetic title ladder from
Beginner Investor to Legendary Investor. Every portfolio is an independent
"game" with its own mode (Beginner/Classic/Expert — nothing ever locked),
per-game XP and level, and optional end date. 14 achievements across
beginner/education/portfolio/strategy/long-term categories, rotating
daily/weekly/monthly challenges with automatic completion detection, a
portfolio report card grading diversification, risk management, research,
returns, patience, and strategy discipline, and a deterministic AI Learning
Coach that turns portfolio observations into learning suggestions (reading
them earns education XP). All of it is opt-out with one toggle (PRD §23).

Previously — **M5 (Strategies, Backtesting & What-If):** Build rule-based
strategies (a symbol universe plus entry/exit conditions templated over each
symbol — price, % move, RSI/SMA/EMA) and backtest them against real daily
history through the exact same rule-evaluation and order/accounting engine
used for live trading. Reports include the equity curve vs benchmark, win/loss
stats, realized P&L, Sharpe/Sortino/beta/max drawdown, performance segmented
by market regime (bull/bear/sideways), open positions, and the full trade
log — with progress streamed while the run executes. The What-If simulator
answers "what if I'd bought NVDA instead?", "what if I never sold?", "what if
I followed every AI recommendation?", and "what if I'd invested monthly?" by
replaying transformed copies of your transaction log against real historical
prices, never touching the actual portfolio.

Previously — **M4 (Local AI):** The AI in AIPTP now runs entirely on
your hardware: a llama.cpp/GGUF model runtime with hardware detection and a
curated model catalog (install/remove/benchmark/hot-switch, per-portfolio or
global default), a **grounded** investment assistant that reasons only over
your real portfolio data and real market data (structured JSON output,
ungrounded suggestions dropped, every recommendation stored with a frozen
snapshot of its inputs), and AI-assisted trading with a review queue —
approve/reject each suggestion, or opt into auto-execution bounded by hard
guardrails (max notional per trade, max trades/day). Every AI trade is
permanently marked AI_ASSISTED/AI_AUTO. Reports now export to PDF and XLSX
including AI recommendation history. Install the inference runtime with
`pip install "./backend[ai]"` (builds llama.cpp; needs cmake + a C compiler);
without it, everything else runs and AI pages report the runtime as absent.

Previously — **M3 (Automation & Deployment):** On top of M1 (core
trading engine, real market data, web UI) and M2 (trailing stops, DCA,
rebalancing, dividends/splits, FX, watchlists, analytics, exports, provider
failover), M3 adds:

- **Automation rules**: a visual rule builder over a safe trigger AST —
  price, % move, SMA/EMA/RSI indicators, cash, allocation, dividend events,
  and UTC schedules, combined with ALL/ANY/NOT — driving buy/sell/notify
  actions with edge-triggering, cooldowns, daily caps, and a full fire log.
  Rules run 24/7 in server mode.
- **Notifications**: in-app inbox, WebSocket push, optional browser/desktop
  notifications.
- **Security v1**: Argon2id login for server deployments (first-run admin
  setup), encrypted-at-rest provider API keys, audit log, automatic daily
  SQLite backups with retention.
- **Deployment**: multi-stage Dockerfile with healthcheck, Compose file with
  persistent volume, one-command launcher (`./deploy/aiptp.sh up`), corporate
  proxy CA support, and a Tauri desktop shell scaffold with a CI installer
  workflow. See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

See [docs/ROADMAP.md](docs/ROADMAP.md) for what lands next (M4: local AI).

### Run it (development)

```bash
# Backend (Python 3.11+)
python3 -m venv .venv
.venv/bin/pip install -e "backend[dev]"

# Frontend (Node 20+) — the server serves the built UI
cd frontend && npm install && npm run build && cd ..

# Start — open http://127.0.0.1:8420
.venv/bin/aiptp
```

Data is stored in `./data/aiptp.db` (SQLite). Configuration via `AIPTP_*`
environment variables (`AIPTP_PORT`, `AIPTP_DATA_DIR`, …). Run the tests with
`cd backend && ../.venv/bin/python -m pytest`.

| Document | Purpose |
| --- | --- |
| [docs/PRD.md](docs/PRD.md) | Product Requirements Document — what we are building and why |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Technical design — stack, components, data model, subsystem designs |
| [docs/ROADMAP.md](docs/ROADMAP.md) | Phased delivery plan mapping PRD requirements to milestones |

## Vision at a Glance

- **Realistic simulation** backed by real market data — no fabricated prices,
  fundamentals, or events.
- **Transparent AI assistance** — every recommendation is explainable, and every
  AI-initiated trade is permanently marked and distinguishable from manual trades.
- **Runs anywhere** — Windows, macOS (Intel and Apple Silicon), and major Linux
  distributions, as a single-user desktop app or a 24/7 multi-user server.
- **Local-first AI** — language models run entirely on the user's hardware, with
  GPU acceleration where available.
- **Automation** — price, indicator, event, and schedule-driven rules that keep
  working in server mode even when no user is connected.
- **Education over speculation** — gamification rewards consistency and learning,
  never trading frequency.

## Core Design Principles

Easy to use · Professional and polished · Fast and responsive · Fully
cross-platform · Highly scalable · Modular · Extensible · Offline-capable where
practical · Server-capable for continuous operation · GPU accelerated whenever
possible · Approachable for beginners, deep enough for experts.

## Repository Layout

```
docs/          Product and technical design documentation
backend/       Core application server (API, simulation, market data, watcher)
frontend/      Web UI (served by the backend when built)
desktop/       Desktop shell wrapping the backend + frontend   (M3)
deploy/        Docker, Compose, and deployment tooling         (M3)
```

## Contributing

Design feedback and issues are welcome — the documents in `docs/` are the
source of truth for scope and architecture.
