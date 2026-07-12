# AIPTP Delivery Roadmap

**Version:** 1.0
**Companion to:** [PRD.md](PRD.md) · [ARCHITECTURE.md](ARCHITECTURE.md)

The PRD describes a very large surface. This roadmap sequences it into phases
where **every phase ends with a usable, coherent product**. Later phases are
additive thanks to the plugin/event-bus architecture — nothing in an early
phase needs rework to enable a later one.

Phase labels (M1, M2, …) are milestones, not calendar commitments.

---

## M1 — Core Simulation Foundation

*Goal: a working paper-trading engine you can actually invest with, locally.*

- Repository scaffolding: backend (FastAPI), frontend (React/TS/Vite), CI.
- Storage layer: SQLAlchemy models + Alembic migrations (SQLite).
- Market Data Abstraction Layer with the first adapter (Yahoo Finance,
  keyless) — quotes, daily/intraday history, Parquet history cache.
- Portfolios: create/edit, cash balances, fractional shares, single currency.
- Trading: market, limit, stop, stop-limit orders; lot-based FIFO/LIFO/Average
  cost accounting; immutable transaction log with `origin` field from day one.
- Price watch scheduler + pending-order evaluation.
- Minimal web UI: dashboard, portfolio view, company page with basic
  interactive price chart (Lightweight Charts), order ticket, transaction
  history.
- REST + WebSocket API skeleton; light/dark themes.

**PRD coverage:** §8, §9 (core), §10 (core), §11 (basic), §12 (basic), §13 (basic).

## M2 — Full Trading & Portfolio Depth

*Goal: brokerage-grade order surface and portfolio insight.*

- Trailing stops, DCA/recurring purchases, percentage-allocation orders,
  mass buy/sell, rebalance, position close/partial sale flows.
- Corporate actions: splits and dividends applied from MDAL data; dividend
  reinvestment option.
- Multi-currency portfolios with FX at execution time.
- Watchlists (multiple), company comparison view.
- Full chart overlay system (buy/sell/dividend/split/earnings markers,
  technical indicators) and synchronized filters.
- Analytics v1: allocation breakdowns, returns, records (best/worst, largest
  gain/loss), win rate, holding periods; risk metrics (Sharpe, Sortino, beta,
  max drawdown, diversification score).
- Reports & export v1: CSV, JSON, Markdown; PDF/XLSX in M4.
- Second and third MDAL adapters (user-keyed) + provider routing/failover.

**PRD coverage:** §9 (complete), §10 (complete), §11–§14, §20, §26 (partial).

## M3 — Automation & Desktop Packaging

*Goal: it works for you while you're away, and installs like a real app.*

- Automation engine: trigger AST, all PRD trigger types, all action types,
  cooldowns/caps, fire log; automation UI (rule builder).
- Notifications: in-app inbox + desktop notifications; event/channel matrix.
- Tauri desktop shell: installers for Windows, macOS (universal), deb/rpm/
  AppImage; embedded server runtime; first-run setup wizard; auto-update.
- Server mode hardening: headless config, login, Dockerfile + Compose +
  one-command launcher, health checks, scheduled backups.
- Security v1: Argon2id auth, encrypted API-key storage, audit log.

**PRD coverage:** §3–§6, §15, §25 (partial), §27 (core).

## M4 — Local AI

*Goal: the "AI" in AIPTP — grounded, explainable, local.*

- Model runtime (llama.cpp/GGUF): hardware detection, model catalog with
  full profiles, install/remove/update/benchmark/compare, hot switching,
  per-portfolio default models.
- AI Investment Assistant: context-pack grounding, structured cited output,
  recommendation persistence with input snapshots, educational disclaimers.
- AI-assisted trading: recommendation review queue, approve/reject flow,
  opt-in auto-execution with guardrails, deterministic expected-impact
  preview; AI-trade visual distinction across all charts/reports.
- GPU acceleration for inference (CUDA/Metal/Vulkan) with CPU fallback;
  Docker GPU passthrough.
- PDF/XLSX export incl. AI recommendation history reports.

**PRD coverage:** §16–§19, §26 (complete), §28 (AI portion).

## M5 — Strategies, Backtesting & What-If

*Goal: test ideas against history with live-engine fidelity.*

- Strategy builder reusing the automation rule AST + universe + sizing.
- Backtest engine sharing live evaluation/execution code paths; worker-pool
  execution with progress streaming; GPU-accelerated batch analytics.
- Backtest reports: return, benchmark comparison, trade log, win/loss,
  drawdown, risk-adjusted metrics, market-condition segmentation.
- What-If simulator: substitute / suppress / adopt-AI-recommendations /
  re-schedule scenarios with comparative reports.

**PRD coverage:** §21, §22, §28 (compute portion).

## M6 — Gamification, Community & Multi-User

*Goal: engagement and sharing, on the platform's education-first terms.*

- XP, levels, achievements, badges, daily/weekly challenges, learning
  objectives, streaks — all opt-out, none frequency-rewarding.
- Server-mode multi-user: roles (admin/trader/viewer), per-user portfolios.
- Community: opt-in anonymous leaderboards, public portfolios, read-only
  share links, friends, monthly competitions, strategy sharing.
- Email notifications.

**PRD coverage:** §23, §24, §25 (complete), §27 (complete).

## Beyond M6 — PRD §30 Future Roadmap

Crypto, ETFs/options/futures simulation, forex, tax estimation, organizations,
voice assistant, mobile apps, public API program, RL research agents, AI
strategy generation — each lands as a plugin or additive module per the
extensibility design (ARCHITECTURE.md §1.2, §29-mapped plugin registry).

---

## Cross-Cutting Tracks (every phase)

- **Testing:** accounting property tests and engine equivalence tests grow
  with each phase; E2E coverage for each new critical path.
- **Accessibility & i18n readiness:** keyboard/ARIA coverage reviewed per
  feature; strings externalized from M1.
- **Performance:** hundreds-of-symbols watch benchmark maintained in CI from
  M1; GPU paths always paired with CPU fallbacks.
- **Docs:** user guide and API reference updated per milestone.
