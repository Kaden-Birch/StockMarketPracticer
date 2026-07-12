# AI Paper Trading Platform (AIPTP)

A modern, cross-platform paper trading application that combines realistic stock
market simulation, advanced analytics, AI-assisted investing, automation,
portfolio management, and gamification into a single application.

All trading uses **simulated funds and simulated positions only**. AIPTP is
designed for education, experimentation, and portfolio analysis — not for
executing real trades.

## Project Status

**Phase: M2 — Full Trading & Portfolio Depth (working).** On top of the M1
core (portfolios, lot-based cost accounting, market/limit/stop orders, price
watcher, REST + WebSocket API, React UI), M2 adds: trailing stops,
dollar-cost-averaging plans that execute 24/7, percent-of-cash/portfolio/
position sizing, one-click rebalancing with preview, batch orders, real
dividend and split application (with optional reinvestment), multi-currency
fills at live FX rates, watchlists, company comparison, analytics (Sharpe,
Sortino, beta, max drawdown, diversification, records), CSV/JSON/Markdown
exports, chart event markers + SMA overlays with synchronized ranges, and a
Yahoo→Stooq→Alpha Vantage provider failover chain. See
[docs/ROADMAP.md](docs/ROADMAP.md) for what lands next.

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
