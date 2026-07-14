# AIPTP Module Architecture (M6.11)

AIPTP is a **modular monolith**: a small Core Platform plus optional feature
Modules that register themselves at startup and communicate only through the
event bus and defined interfaces. Adding a feature means adding a module — the
core never changes. This implements roadmap §6.11.

## Layers

```
User Interface  (assembles nav/tabs from /api/v1/modules)
      │
Experience Framework  (per-portfolio presets gate module behavior)
      │
Module Manager  (load → validate deps → register → start; error isolation)
      │
Core Platform  ·  Optional Modules
```

## Core Platform (never depends on a module)

Portfolios, trading engine, market-data abstraction layer, analytics, AI model
manager, storage, auth, settings/config, the API layer, the event bus, the
module manager, and the experience framework. Lives in `aiptp/` outside
`aiptp/modules/`.

## Module Manager (`aiptp/core/modules.py`)

Loads modules in dependency order, validates dependencies (cascade-disables
dependents of a disabled/failed module with a clear reason), runs the
lifecycle, and **isolates failures** — a module that raises during start is
marked `FAILED` and skipped; the app keeps running. Scheduler jobs contributed
by modules are wrapped so a crashing job can't take the scheduler down.

Lifecycle: `initialize` (wire routers/services) → `register_events` (subscribe
to the bus) → `start` (schedule jobs) → running. Toggling a module persists a
setting and takes effect on the next restart (routers/jobs are wired at boot).

Manage via `GET /api/v1/modules` and `PUT /api/v1/modules/{id}`.

## Event Bus (`aiptp/core/events.py`)

Publishers emit typed events; modules subscribe to the types they care about.
Two delivery paths: internal handlers (synchronous, per-handler error
isolation) and WebSocket fanout to clients. A publisher mid-transaction passes
its DB session so DB-writing handlers (e.g. the inbox) join that transaction
instead of opening a second SQLite writer and self-deadlocking.

Key events: `order_filled`, `watch.quotes`, `rule_fired`, `recurring_executed`,
`corporate_action`, `achievement`, `challenge`, `level_up`, `ai_analysis`,
`notification`, `backtest_progress`, `backtest_done`.

## Experience Presets (`aiptp/core/presets.py`)

Every portfolio has a preset that gates which modules act on it:

| Preset | Gamification | Notes |
|---|---|---|
| **Academy** (default) | on | Everything enabled |
| **Learning** | off | Mentor + analytics; no XP/levels/achievements |
| **Professional** | off | Clean analytics/reporting; no cosmetic rewards |

Presets are orthogonal to **experience levels** (Beginner/Classic/Expert,
stored as `Portfolio.mode`), which change *how* modules present, not *which*
are active.

## Built-in modules (`aiptp/modules/`)

| Module | Deps | Permissions | Publishes | Consumes |
|---|---|---|---|---|
| `notifications` | — | SendNotifications, ReadPortfolio | notification | order_filled, rule_fired, recurring_executed, corporate_action, achievement, challenge, level_up, ai_analysis |
| `automation` | — | Read/ModifyPortfolio, ReadHistorical | rule_fired, recurring_executed | watch.quotes |
| `gamification` | — | ReadPortfolio, ReadHistorical | achievement, challenge, level_up | — |
| `ai_mentor` | — | Read/ModifyPortfolio, AccessAIModels | ai_analysis | — |
| `reporting` | — | ReadPortfolio, ReadHistorical | — | — |
| `multiplayer` | — | Read/ModifyPortfolio, AccessMultiplayer | order_filled | — |
| `leaderboards` | — | ReadPortfolio, ReadHistorical | — | — |
| `discord` | notifications | ReadPortfolio, SendNotifications | — | order_filled, achievement, challenge, level_up, ai_analysis, competition |
| `scenarios` | — | Read/ModifyPortfolio, ReadHistorical | — | — |
| `career` | — | ReadPortfolio, ReadHistorical | — | — |
| `classroom` | scenarios | Read/ModifyPortfolio, AccessMultiplayer | — | — |

Each contributes UI (nav items / portfolio tabs / settings pages) that the
frontend renders only when the module is running.

### Known limitations

- Enable/disable applies on the next restart (routers and scheduler jobs are
  wired at boot), reported as a pending change until then.
- Third-party/sandboxed plugins are future; today's modules are first-party and
  trusted. Permissions are declared and surfaced but not yet enforced as a
  sandbox.

## Provider abstractions

- **AI runtimes** (`aiptp/ai/runtime.py`, roadmap 6.11.13): `LlamaCppRuntime`
  (local GGUF), `OpenAICompatibleRuntime` (Ollama / LM Studio / OpenAI-compatible
  endpoints), `FakeRuntime` (tests), selected by `AIPTP_AI_RUNTIME`. The rest of
  the app talks only to the runtime interface.
- **Notification channels** (`aiptp/notify/channels.py`, roadmap 6.11.14):
  Discord / Slack / generic webhook behind one interface; Email/Telegram/SMS
  slot in later. Configured under the Notifications module's settings.
- **Execution** (future, roadmap 6.11.15): portfolio logic already funnels
  every fill through `trading/engine.py`; a broker-execution provider seam slots
  in there without touching portfolio logic. Only paper trading exists today.

## Adding a module

1. Add `aiptp/modules/<name>_module.py` with a `Manifest` and lifecycle hooks.
2. List it in `aiptp/modules/__init__.py:build_modules()`.
3. It registers its own routers, events, jobs, and UI contributions — no core
   edits. Test it in isolation with a `FakeRuntime`/`FakeProvider` and mock
   event injection.
