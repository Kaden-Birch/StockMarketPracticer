# AI Paper Trading Platform (AIPTP)

A modern, cross-platform paper trading application that combines realistic stock
market simulation, advanced analytics, AI-assisted investing, automation,
portfolio management, and gamification into a single application.

All trading uses **simulated funds and simulated positions only**. AIPTP is
designed for education, experimentation, and portfolio analysis — not for
executing real trades.

## Project Status

**Phase: M6 — Gamification, Progression & Learning (working).** A permanent
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
