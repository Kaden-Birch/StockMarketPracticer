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





---
## M6 and Beyond.
M6 — Gamification, Progression & Personal Learning Experience
Goal

Introduce engaging game mechanics that encourage users to learn investing concepts, develop good portfolio habits, and improve their financial knowledge.

Gamification must reinforce:

Learning
Research
Long-term thinking
Risk management
Portfolio discipline

Gamification must not reward:

Excessive trading
Gambling behavior
Short-term speculation
High-risk strategies purely for points
6.1 User Profile System

Create a permanent user profile independent of individual investment games.

Profile stores:
Username
Avatar
Profile level
XP
Achievements
Titles
Badges
Completed lessons
Knowledge progress
Historical performance
Statistics
6.2 Profile Level System

Profile level represents the user's overall investing experience.

Profile XP is earned through:

Education XP

Examples:

Completing lessons
Reading company information
Completing quizzes
Learning new concepts
Research XP

Examples:

Reviewing financial statements
Comparing companies
Using analytics tools
Performing portfolio analysis
Portfolio XP

Examples:

Maintaining diversification
Managing risk
Achieving investment goals
Following strategies successfully
Challenge XP

Examples:

Completing scenarios
Participating in competitions
Finishing objectives
6.3 Profile Titles

Cosmetic titles only.

Examples:

Beginner Investor

↓

Market Student

↓

Retail Investor

↓

Analyst

↓

Portfolio Manager

↓

Fund Manager

↓

Institutional Investor

↓

Legendary Investor

6.4 Independent Game System

Users can create unlimited investment simulations.

Each game contains:

Portfolio
Starting capital
Rules
Mode
Duration
Challenges
Achievements
Statistics
History

Example:

Game 1:
$100,000 Growth Portfolio

Game 2:
$50,000 Dividend Challenge

Game 3:
2008 Financial Crisis Simulation
6.5 Game Level System

Each individual game has its own progression.

Example:

User Profile Level:
25

Growth Portfolio:
Level 14

Dividend Portfolio:
Level 8

Expert Competition:
Level 3

Game level tracks progress within that specific simulation.

6.6 Game Modes
Beginner Mode
Purpose

Teach new investors.

Features:
Guided onboarding
Simplified dashboards
Contextual explanations
AI coaching
Suggested learning paths
Beginner challenges

Important:

Features are not permanently locked.

Advanced users can enable advanced tools manually.

Classic Mode
Purpose

Default experience.

Includes:

Full analytics
XP system
Achievements
Challenges
AI assistance
Complete trading tools
Expert Mode
Purpose

Experienced investors.

Everything available immediately.

Includes:

Advanced analytics
Full statistics
Automation
Strategy tools
AI tools
Backtesting
Advanced charts

No tutorials or guided introductions.

6.7 Achievement System

Achievements reward meaningful progress.

Categories:

Beginner
First investment
First profit
First dividend
Education
Complete 10 lessons
Analyze 50 companies
Learn 100 concepts
Portfolio
Diversified portfolio
Beat benchmark
Survive market crash
Strategy
Create first strategy
Complete backtest
Execute successful strategy
Long-Term
Hold investment for one year
Maintain portfolio discipline
6.8 Challenge System
Daily Challenges

Examples:

Review one company
Learn one concept
Analyze portfolio allocation
Weekly Challenges

Examples:

Build diversified portfolio
Compare companies
Review earnings
Monthly Challenges

Examples:

Beat benchmark
Reduce portfolio risk
Complete strategy goals
6.9 Portfolio Report Card

Generate periodic evaluations.

Metrics:

Diversification
Risk management
Research
Returns
Patience
Strategy discipline

Example:

Diversification: A-
Research: B+
Risk Management: A
Patience: C+
6.10 AI Learning Coach Foundation

Provides:

Portfolio observations
Learning suggestions
Risk explanations
Educational recommendations

Examples:

"You are heavily concentrated in technology stocks."

"Would you like to learn about diversification?"

M6.11 — Modular Platform Architecture & Experience Framework

Goal

Refactor the application into a modular, plugin-oriented architecture that separates the core trading engine from optional functionality.

This milestone establishes the long-term foundation for every future feature by allowing systems such as gamification, AI mentoring, multiplayer, notifications, Discord integration, and educational content to operate as independent modules that can be enabled, disabled, or extended without modifying the application's core logic.

M6.11 must be completed before M7 begins.

Design Goals

The architecture should prioritize:

Modularity
Extensibility
Cross-platform compatibility
Maintainability
Scalability
Testability
Performance

Future milestones should primarily involve creating new modules rather than changing existing core systems.

Core Design Philosophy

Separate the platform into two major layers.

    User Interface
        |
    Experience Framework
        |
    Module Manager
        |
    Core Platform  +  Optional Modules

The Core Platform should never directly depend on optional systems.

6.11.1 Core Platform

The Core Platform contains only functionality required for every installation.

Core Components:

User management
Authentication
Portfolio engine
Trading engine
Market data engine
Data storage
Company database
AI model manager
Analytics engine
Settings system
Configuration system
API layer
Plugin manager
Experience framework

These components should have zero dependencies on gamification or social systems.

6.11.2 Module Architecture

Every major feature should be implemented as a self-contained module. Modules communicate through well-defined interfaces and events.

Gamification Module
AI Mentor Module
Knowledge Base Module
Discord Module
Notification Module
Multiplayer Module
AI Competitor Module
Leaderboards Module
Reporting Module
Classroom Module
Historical Scenarios Module
Automation Module

A module should never directly modify another module's internal state. Instead, communication occurs through the event system.

6.11.3 Plugin Framework

All modules should behave as plugins. Plugins may be built-in, first-party, or third-party (future).

Each plugin should define: Name, Version, Dependencies, Permissions, Configuration, Settings UI, Events listened to, Events published.

    plugin:
      name: Discord Integration
      version: 1.0.0
      dependencies:
        - Notifications
      permissions:
        - ReadPortfolio
        - SendNotifications
        - ReadAchievements

6.11.4 Event Bus

The platform should use an internal event-driven architecture.

Events include: TradeExecuted, PortfolioUpdated, AchievementUnlocked, ChallengeCompleted, AIRecommendationGenerated, MarketOpened, MarketClosed, LessonCompleted, ScenarioFinished, UserLoggedIn.

Modules subscribe only to events they care about:

    Trade Executed -> Portfolio Engine -> Publish Event -> Event Bus
      -> Gamification Module
      -> Discord Module
      -> Notifications Module
      -> Analytics Module
      -> AI Mentor

6.11.5 Experience Framework

Every portfolio uses an Experience Preset. Experience Presets determine which modules are active.

Learning — education-focused.
  Enabled: AI Mentor, Analytics, Portfolio, Knowledge Base, Historical Scenarios.
  Disabled: XP, Levels, Achievements, Leaderboards, Seasonal events.

Academy — everything enabled. Default preset.

Professional — focus on clean analytics.
  Enabled: Reporting, Portfolio, AI Mentor, Classroom, Historical Scenarios.
  Disabled: Gamification, Cosmetic rewards, Seasonal competitions.

6.11.6 Experience Levels

Separate from Experience Presets. Every portfolio selects Beginner, Classic, or Expert. The preset defines which modules are available. The level defines how the user experiences them.

6.11.7 Module Manager

The Module Manager is responsible for: loading modules, validating dependencies, registering events, registering settings, initializing services, safe shutdown, and error isolation.

If one module crashes, the application should continue running whenever possible.

6.11.8 Module Lifecycle

Every module should implement a standard lifecycle:

    Load -> Initialize -> Register Events -> Start -> Running
         -> Pause -> Resume -> Shutdown -> Unload

6.11.9 Module Permissions

Modules should request explicit permissions: Read Portfolio, Modify Portfolio, Read Company Data, Send Notifications, Access AI Models, Access Multiplayer, Read Historical Data.

Future third-party plugins should be sandboxed using these permissions.

6.11.10 Settings Registration

Modules register their own settings pages.

    Settings
      Core | Appearance | AI | Portfolio | Discord | Notifications
      | Gamification | Multiplayer | Classroom

The core UI never needs updating when new modules are added.

6.11.11 Dependency Management

Modules declare dependencies (e.g. Discord -> Notifications -> Core). If Notifications is disabled, Discord features depending on it should automatically disable with a clear explanation.

6.11.12 UI Contribution System

Modules can contribute: navigation items, dashboard widgets, context menus, toolbar buttons, portfolio tabs, settings pages, notification types.

The core UI dynamically assembles itself based on enabled modules.

6.11.13 AI Provider Abstraction

AI providers should also be plugins: Ollama, LM Studio, OpenAI-compatible APIs, llama.cpp, future providers. The rest of the application talks only to the AI abstraction layer.

6.11.14 Notification Providers

Notification systems should be modular: Email, Discord, Slack, Microsoft Teams, Telegram, Push Notifications, SMS (future).

6.11.15 Broker Integrations (Future)

Future real trading support should use the same architecture: Paper Trading, Interactive Brokers, Alpaca, Wealthsimple, Questrade, Schwab. Portfolio logic should not care which execution provider is active.

6.11.16 Testing Requirements

Every module should support unit testing, integration testing, mock event injection, and independent execution where practical. Modules should be testable in isolation.

6.11.17 Documentation Requirements

Each module must include: purpose, dependencies, public API, published events, consumed events, settings, permissions, known limitations.

6.11.18 Success Criteria

M6.11 is complete when:

The application runs using the new modular architecture.
M6 features have been migrated into modules.
Experience Presets can enable or disable entire modules without code changes.
The UI automatically adapts based on active modules.
New modules can be added without modifying the core application.
Modules communicate exclusively through the event bus or defined interfaces.
AI providers, notification providers, and future broker integrations all use the same plugin abstraction.
A module failure does not bring down the entire application whenever graceful degradation is possible.

M7 — Multiplayer, Community & External Integrations
Goal

Allow users to compete, collaborate, and share investment simulations.

7.1 Multiplayer Games

Support:

Private games
Friend competitions
Public competitions
Investment clubs
7.2 Multiplayer Modes
Competitive

Players compete based on:

Returns
Risk-adjusted returns
Diversification
Strategy quality
Cooperative

Players manage shared portfolios.

Features:

Roles
Permissions
Voting
Shared decisions
Educational

Designed for:

Classes
Groups
Training environments
7.3 Leaderboards

Categories:

Highest return
Best risk-adjusted performance
Best diversification
Best beginner improvement
Lowest drawdown
Best strategy
7.4 Investment Clubs

Features:

Shared discussions
Shared challenges
Club portfolios
Rankings
Strategy sharing
7.5 Discord Integration

Full Discord bot.

Configured through application UI.

No command line configuration.

Discord Features

Notifications:

Trades executed
AI recommendations
Achievements
Challenges
Portfolio summaries
Competition updates
Discord Commands

Examples:

/portfolio

/performance

/company

/leaderboard

/challenge

/summary
Discord Roles

Automatic role assignment:

Beginner Investor
Analyst
Portfolio Manager
Competition Winner
7.6 Sharing

Support:

Public portfolios
Anonymous profiles
Read-only links
Strategy sharing
M8 — Advanced Learning Ecosystem & AI Mentor
Goal

Create a personalized investing education system powered by AI.

8.1 Persistent AI Mentor

The AI mentor understands:

Portfolio history
User behavior
Mistakes
Strengths
Knowledge gaps
Investment style

Examples:

"You often sell winners too early."

"Your portfolio lacks international exposure."

"You have not reviewed valuation metrics yet."

8.2 Historical Market Scenarios

Replay real historical periods.

Examples:

Dot-com crash
2008 financial crisis
COVID crash
Inflation cycles
Technology booms

Players start without future knowledge.

Compare:

User
Market
AI strategies
Other players
8.3 Career Mode

Investment career progression.

Ranks:

Intern Investor

↓

Retail Investor

↓

Portfolio Manager

↓

Fund Manager

↓

Institutional Investor

Objectives:

Manage risk
Beat benchmarks
Follow mandates
Protect investors
8.4 Portfolio Mandates

Scenario restrictions.

Examples:

Retirement Fund

Requirements:

Low volatility
Diversification
Growth Fund

Requirements:

Higher growth
Higher risk
Dividend Fund

Requirements:

Minimum dividend yield
Technology Fund

Requirements:

Sector restrictions
8.5 Advanced Challenges

Examples:

Beat the market
Survive recession
Manage billion-dollar portfolio
Recover from crash
8.6 Classroom Mode

Features:

Instructor dashboard
Student portfolios
Assignments
Progress tracking
Custom scenarios
M9 — AI Investment Competitors & Simulated Opponents
Goal

Provide realistic competition for users without requiring friends.

AI opponents simulate different investing philosophies.

9.1 AI Competitor Games

Users can create games with:

Human players
AI players
Mixed teams
9.2 AI Investor Profiles

Default competitors:

Conservative Investor

Focus:

Stability
Dividends
ETFs
Low volatility
Growth Investor

Focus:

Technology
Emerging companies
High growth
Value Investor

Focus:

Undervalued companies
Fundamentals
Dividend Investor

Focus:

Income
Dividend growth
Technical Trader

Focus:

Indicators
Momentum
Quant Investor

Focus:

Data models
Statistics
Algorithms
Market Timer

Focus:

Economic cycles
Market timing
Beginner Investor

Purpose:

Educational opponent.

Makes common mistakes.

9.3 AI Difficulty Levels
Beginner AI

Educational.

Makes mistakes.

Explains decisions.

Intermediate AI

Average investor behavior.

Advanced AI

Strong strategy.

Expert AI

Optimized decision-making.

9.4 AI Personality System

AI behavior controlled by:

Risk tolerance
Patience
Confidence
Conviction
Adaptability
9.5 AI Transparency

Every AI action shows:

Decision
Reason
Data used
Confidence
Expected outcome
9.6 AI Post-Game Analysis

Reports:

Why you won
Why you lost
What strategies worked
What mistakes occurred
9.7 Adaptive AI

AI opponents learn from:

User behavior
Portfolio choices
Trading patterns
9.8 AI Tournaments

Examples:

Beat the Market
Growth vs Value
Human vs AI
9.9 Historical AI Opponents

Compete against:

Index funds
Dividend strategies
Growth strategies
Value strategies
Momentum strategies
M10 — Investment Knowledge Base & Interactive Learning System
Goal

Create a built-in financial education system allowing anyone to understand investing concepts.

10.1 Investment Dictionary

Searchable database of:

Terms
Concepts
Strategies
Metrics
Events

Examples:

Diversification
P/E Ratio
Beta
Dollar Cost Averaging
Market Cap
10.2 Multi-Level Explanations

Every concept includes:

Beginner Explanation

Simple language.

Intermediate Explanation

More technical explanation.

Advanced Explanation

Professional-level explanation.

10.3 Contextual Learning

The system detects learning opportunities.

Examples:

User has:

100% Canadian stocks.

Prompt:

"Learn why investors diversify geographically."

User owns:

80% technology stocks.

Prompt:

"Learn about concentration risk."

10.4 AI Explanations

Users can ask:

Explain simply
Give examples
Explain impact on my portfolio
Compare concepts
10.5 Interactive Simulations

Examples:

Diversification simulator.

Risk simulator.

Market crash simulator.

Compound growth simulator.

10.6 Knowledge Categories
Investing Basics
Stocks
ETFs
Bonds
Dividends
Portfolio Management
Diversification
Allocation
Rebalancing
Risk
Financial Metrics
EPS
P/E
Revenue
Cash flow
Technical Analysis
RSI
MACD
Moving averages
Economics
Inflation
Interest rates
GDP
Strategies
Growth
Value
Dividend
Index investing
10.7 Knowledge Tracking

Track:

Concepts viewed
Lessons completed
Quiz results
Knowledge categories
10.8 Learning Achievements

Examples:

Learned first investing concept
Completed fundamentals
Portfolio management expert
Market history expert
10.9 AI Mentor Integration

AI recommends learning based on:

Portfolio behavior
Mistakes
Knowledge gaps
10.10 Universal Glossary Integration

Every investing term throughout the application is clickable.

Example:

Beta: 1.35 ❔

Click:

Explanation opens.

10.11 Quizzes

Optional quizzes after lessons.

10.12 Learning Paths

Prebuilt paths:

Beginner Investor
What are stocks?
How markets work
Risk
Diversification
Intermediate Investor
Valuation
Financial statements
Portfolio construction
Advanced Investor
Factor investing
Quant strategies
Risk optimization
Final M6–M10 Philosophy
M6

Make investing fun.

M7

Make investing social.

M8

Make investing personal.

M9

Make investing competitive.

M10

Make investing understandable.

Together these milestones transform the application from a paper trading simulator into a complete AI-powered investment education platform.
