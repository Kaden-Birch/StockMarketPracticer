# AI Paper Trading Platform (AIPTP)

A modern, cross-platform paper trading application that combines realistic stock
market simulation, advanced analytics, AI-assisted investing, automation,
portfolio management, and gamification into a single application.

All trading uses **simulated funds and simulated positions only**. AIPTP is
designed for education, experimentation, and portfolio analysis — not for
executing real trades.

## Project Status

**Phase: Design.** This repository currently contains the product and technical
design documentation that will drive implementation.

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

## Repository Layout (planned)

```
docs/          Product and technical design documentation
backend/       Core application server (API, simulation, automation, AI)
frontend/      Web UI (also embedded by the desktop shell)
desktop/       Desktop shell wrapping the backend + frontend
deploy/        Docker, Compose, and deployment tooling
```

## Contributing

Implementation has not started yet. Design feedback is welcome — open an issue
against the documents in `docs/`.
