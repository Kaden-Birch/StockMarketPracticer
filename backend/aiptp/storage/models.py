import enum
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base, DecimalStr


def _uuid() -> str:
    return uuid.uuid4().hex


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class CostBasisMethod(str, enum.Enum):
    FIFO = "FIFO"
    LIFO = "LIFO"
    AVERAGE = "AVERAGE"


class OrderSide(str, enum.Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, enum.Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"
    STOP_LIMIT = "STOP_LIMIT"
    TRAILING_STOP = "TRAILING_STOP"


class OrderStatus(str, enum.Enum):
    PENDING = "PENDING"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


class Origin(str, enum.Enum):
    """Provenance of an order/transaction. AI and automation variants exist
    from day one so AI-assisted trades are distinguishable at the data layer
    forever (PRD §17); M1 only produces MANUAL."""

    MANUAL = "MANUAL"
    AUTOMATION = "AUTOMATION"
    AI_ASSISTED = "AI_ASSISTED"
    AI_AUTO = "AI_AUTO"
    SYSTEM = "SYSTEM"  # corporate actions applied by the platform
    DIVIDEND_REINVEST = "DIVIDEND_REINVEST"


class TransactionKind(str, enum.Enum):
    TRADE = "TRADE"
    DIVIDEND = "DIVIDEND"  # cash dividend credit
    SPLIT = "SPLIT"  # share-quantity adjustment, no cash movement


class PercentOf(str, enum.Enum):
    CASH = "CASH"
    PORTFOLIO ="PORTFOLIO"
    POSITION = "POSITION"  # sells: percentage of current holding


class Cadence(str, enum.Enum):
    DAILY = "DAILY"
    WEEKLY = "WEEKLY"
    MONTHLY = "MONTHLY"


class GameMode(str, enum.Enum):
    BEGINNER = "BEGINNER"
    CLASSIC = "CLASSIC"
    EXPERT = "EXPERT"


class Portfolio(Base):
    __tablename__ = "portfolios"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    # Multi-user ownership (M7): "local" in desktop mode; a username in
    # server mode. Access = owner, portfolio member, or admin.
    owner: Mapped[str] = mapped_column(String(80), default="local")
    public_on_leaderboard: Mapped[bool] = mapped_column(default=False)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")
    currency: Mapped[str] = mapped_column(String(8), default="USD")
    starting_balance: Mapped[Decimal] = mapped_column(DecimalStr)
    cash_balance: Mapped[Decimal] = mapped_column(DecimalStr)
    cost_basis_method: Mapped[CostBasisMethod] = mapped_column(
        Enum(CostBasisMethod), default=CostBasisMethod.FIFO
    )
    dividend_reinvest: Mapped[bool] = mapped_column(default=False)
    # AI-assisted trading settings (PRD §17): auto-execution is opt-in and
    # bounded by hard guardrails.
    ai_auto_execute: Mapped[bool] = mapped_column(default=False)
    ai_max_trade_notional: Mapped[Decimal] = mapped_column(
        DecimalStr, default=Decimal("1000")
    )
    ai_max_trades_per_day: Mapped[int] = mapped_column(default=3)
    ai_default_model: Mapped[str] = mapped_column(String(80), default="")
    # Each portfolio is an independent "game" (roadmap 6.4-6.6): its own
    # mode, progression, and optional end date.
    mode: Mapped[GameMode] = mapped_column(Enum(GameMode), default=GameMode.CLASSIC)
    # Experience preset (roadmap 6.11.5): which modules act on this portfolio.
    preset: Mapped[str] = mapped_column(String(20), default="ACADEMY")
    game_xp: Mapped[int] = mapped_column(default=0)
    # M8.4: optional mandate ("" | retirement | growth | dividend | technology)
    # — compliance is reported, never force-liquidated.
    mandate: Mapped[str] = mapped_column(String(20), default="")
    # M11: optional grouping into an isolated "game" space.
    game_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # M8.2: set when this is a historical-scenario game portfolio. Scenario
    # portfolios trade at historical closes and are excluded from live
    # listings, the watcher, and live corporate actions.
    scenario_session_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    holdings: Mapped[list["Holding"]] = relationship(
        back_populates="portfolio", cascade="all, delete-orphan"
    )
    orders: Mapped[list["Order"]] = relationship(
        back_populates="portfolio", cascade="all, delete-orphan"
    )
    transactions: Mapped[list["Transaction"]] = relationship(
        back_populates="portfolio", cascade="all, delete-orphan"
    )


class Holding(Base):
    __tablename__ = "holdings"
    __table_args__ = (Index("ix_holdings_portfolio_symbol", "portfolio_id", "symbol", unique=True),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    portfolio_id: Mapped[str] = mapped_column(ForeignKey("portfolios.id", ondelete="CASCADE"))
    symbol: Mapped[str] = mapped_column(String(20))
    quantity: Mapped[Decimal] = mapped_column(DecimalStr, default=Decimal("0"))

    portfolio: Mapped[Portfolio] = relationship(back_populates="holdings")
    lots: Mapped[list["Lot"]] = relationship(
        back_populates="holding", cascade="all, delete-orphan", order_by="Lot.acquired_at"
    )


class Lot(Base):
    """A tax lot. Lot-level tracking makes FIFO/LIFO/Average exact, including
    fractional shares and partial sales."""

    __tablename__ = "lots"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    holding_id: Mapped[str] = mapped_column(ForeignKey("holdings.id", ondelete="CASCADE"))
    quantity_remaining: Mapped[Decimal] = mapped_column(DecimalStr)
    unit_cost: Mapped[Decimal] = mapped_column(DecimalStr)
    acquired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    holding: Mapped[Holding] = relationship(back_populates="lots")


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (Index("ix_orders_status_symbol", "status", "symbol"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    portfolio_id: Mapped[str] = mapped_column(ForeignKey("portfolios.id", ondelete="CASCADE"))
    symbol: Mapped[str] = mapped_column(String(20))
    side: Mapped[OrderSide] = mapped_column(Enum(OrderSide))
    type: Mapped[OrderType] = mapped_column(Enum(OrderType))
    quantity: Mapped[Decimal | None] = mapped_column(DecimalStr, nullable=True)
    notional: Mapped[Decimal | None] = mapped_column(DecimalStr, nullable=True)
    limit_price: Mapped[Decimal | None] = mapped_column(DecimalStr, nullable=True)
    stop_price: Mapped[Decimal | None] = mapped_column(DecimalStr, nullable=True)
    stop_triggered: Mapped[bool] = mapped_column(default=False)
    trail_amount: Mapped[Decimal | None] = mapped_column(DecimalStr, nullable=True)
    trail_percent: Mapped[Decimal | None] = mapped_column(DecimalStr, nullable=True)
    watermark: Mapped[Decimal | None] = mapped_column(DecimalStr, nullable=True)
    percent: Mapped[Decimal | None] = mapped_column(DecimalStr, nullable=True)
    percent_of: Mapped[PercentOf | None] = mapped_column(Enum(PercentOf), nullable=True)
    status: Mapped[OrderStatus] = mapped_column(Enum(OrderStatus), default=OrderStatus.PENDING)
    reject_reason: Mapped[str] = mapped_column(Text, default="")
    origin: Mapped[Origin] = mapped_column(Enum(Origin), default=Origin.MANUAL)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    filled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    portfolio: Mapped[Portfolio] = relationship(back_populates="orders")


class Transaction(Base):
    """Immutable, append-only record of every fill. Never updated or deleted;
    corrections are compensating entries."""

    __tablename__ = "transactions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    portfolio_id: Mapped[str] = mapped_column(ForeignKey("portfolios.id", ondelete="CASCADE"))
    order_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    symbol: Mapped[str] = mapped_column(String(20))
    side: Mapped[OrderSide] = mapped_column(Enum(OrderSide))
    quantity: Mapped[Decimal] = mapped_column(DecimalStr)
    price: Mapped[Decimal] = mapped_column(DecimalStr)
    amount: Mapped[Decimal] = mapped_column(DecimalStr)
    fees: Mapped[Decimal] = mapped_column(DecimalStr, default=Decimal("0"))
    realized_pnl: Mapped[Decimal | None] = mapped_column(DecimalStr, nullable=True)
    kind: Mapped[TransactionKind] = mapped_column(
        Enum(TransactionKind), default=TransactionKind.TRADE
    )
    fx_rate: Mapped[Decimal] = mapped_column(DecimalStr, default=Decimal("1"))
    quote_currency: Mapped[str] = mapped_column(String(8), default="USD")
    origin: Mapped[Origin] = mapped_column(Enum(Origin), default=Origin.MANUAL)
    executed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    portfolio: Mapped[Portfolio] = relationship(back_populates="transactions")


class RecurringPlan(Base):
    """Dollar-cost-averaging / recurring purchase plan. Executed by the
    scheduler when next_run_at passes; runs 24/7 in server mode."""

    __tablename__ = "recurring_plans"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    portfolio_id: Mapped[str] = mapped_column(ForeignKey("portfolios.id", ondelete="CASCADE"))
    symbol: Mapped[str] = mapped_column(String(20))
    amount: Mapped[Decimal] = mapped_column(DecimalStr)  # notional, portfolio currency
    cadence: Mapped[Cadence] = mapped_column(Enum(Cadence))
    next_run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    enabled: Mapped[bool] = mapped_column(default=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    run_count: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Watchlist(Base):
    __tablename__ = "watchlists"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    items: Mapped[list["WatchlistItem"]] = relationship(
        back_populates="watchlist", cascade="all, delete-orphan", order_by="WatchlistItem.added_at"
    )


class WatchlistItem(Base):
    __tablename__ = "watchlist_items"
    __table_args__ = (
        Index("ix_watchlist_items_unique", "watchlist_id", "symbol", unique=True),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    watchlist_id: Mapped[str] = mapped_column(ForeignKey("watchlists.id", ondelete="CASCADE"))
    symbol: Mapped[str] = mapped_column(String(20))
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    watchlist: Mapped[Watchlist] = relationship(back_populates="items")


class RecommendationStatus(str, enum.Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    EXECUTED = "EXECUTED"


class RecommendationAction(str, enum.Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


class Recommendation(Base):
    """An AI suggestion, permanently explainable: inputs_snapshot freezes the
    exact data the model saw (PRD §16), and executed trades are forever
    marked AI_ASSISTED/AI_AUTO through the order origin (PRD §17)."""

    __tablename__ = "recommendations"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    portfolio_id: Mapped[str] = mapped_column(ForeignKey("portfolios.id", ondelete="CASCADE"))
    model_id: Mapped[str] = mapped_column(String(80))
    action: Mapped[RecommendationAction] = mapped_column(Enum(RecommendationAction))
    symbol: Mapped[str] = mapped_column(String(20), default="")
    sizing: Mapped[str] = mapped_column(Text, default="{}")  # {"notional": "..."} etc.
    rationale: Mapped[str] = mapped_column(Text, default="")
    confidence: Mapped[Decimal | None] = mapped_column(DecimalStr, nullable=True)  # 0-1
    analysis: Mapped[str] = mapped_column(Text, default="")  # full analysis text
    inputs_snapshot: Mapped[str] = mapped_column(Text, default="{}")  # JSON context pack
    expected_impact: Mapped[str] = mapped_column(Text, default="{}")  # deterministic JSON
    status: Mapped[RecommendationStatus] = mapped_column(
        Enum(RecommendationStatus), default=RecommendationStatus.PENDING
    )
    executed_order_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Strategy(Base):
    """Rule-based strategy (PRD §22): the automation trigger AST templated
    with "$SYMBOL", applied to every symbol in the universe. Backtests share
    the live evaluation and execution code paths."""

    __tablename__ = "strategies"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")
    universe: Mapped[str] = mapped_column(Text)  # JSON list of symbols
    entry_trigger: Mapped[str] = mapped_column(Text)  # JSON AST, $SYMBOL templated
    exit_trigger: Mapped[str | None] = mapped_column(Text, nullable=True)
    entry_notional: Mapped[Decimal] = mapped_column(DecimalStr, default=Decimal("1000"))
    initial_cash: Mapped[Decimal] = mapped_column(DecimalStr, default=Decimal("10000"))
    benchmark: Mapped[str] = mapped_column(String(20), default="SPY")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class BacktestStatus(str, enum.Enum):
    RUNNING = "RUNNING"
    DONE = "DONE"
    FAILED = "FAILED"


class BacktestRun(Base):
    __tablename__ = "backtest_runs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    strategy_id: Mapped[str] = mapped_column(ForeignKey("strategies.id", ondelete="CASCADE"))
    range: Mapped[str] = mapped_column(String(8), default="1Y")
    status: Mapped[BacktestStatus] = mapped_column(
        Enum(BacktestStatus), default=BacktestStatus.RUNNING
    )
    progress_pct: Mapped[int] = mapped_column(default=0)
    error: Mapped[str] = mapped_column(Text, default="")
    results: Mapped[str] = mapped_column(Text, default="{}")  # JSON report
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Profile(Base):
    """Permanent user profile (roadmap 6.1) — independent of any single game.
    Single-row until multi-user lands in M7. XP is categorized (roadmap 6.2)
    and never rewards trading frequency (PRD §23)."""

    __tablename__ = "profiles"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    username: Mapped[str] = mapped_column(String(80), default="Investor")
    avatar: Mapped[str] = mapped_column(String(16), default="📈")
    education_xp: Mapped[int] = mapped_column(default=0)
    research_xp: Mapped[int] = mapped_column(default=0)
    portfolio_xp: Mapped[int] = mapped_column(default=0)
    challenge_xp: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class XpEvent(Base):
    """Append-only XP audit trail; also drives anti-abuse daily caps."""

    __tablename__ = "xp_events"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    category: Mapped[str] = mapped_column(String(20))  # education|research|portfolio|challenge
    kind: Mapped[str] = mapped_column(String(60))  # e.g. company_viewed, challenge:daily_review
    amount: Mapped[int] = mapped_column()
    reason: Mapped[str] = mapped_column(String(200), default="")
    portfolio_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class EarnedAchievement(Base):
    __tablename__ = "earned_achievements"
    __table_args__ = (Index("ix_earned_achievement_unique", "achievement_id", unique=True),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    achievement_id: Mapped[str] = mapped_column(String(60))
    portfolio_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    earned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ChallengeStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"


class ChallengeAssignment(Base):
    """A challenge assigned for a specific period (roadmap 6.8). period_key
    is the day (2026-07-12), ISO week (2026-W28), or month (2026-07)."""

    __tablename__ = "challenge_assignments"
    __table_args__ = (
        Index("ix_challenge_period_unique", "challenge_id", "period_key", unique=True),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    challenge_id: Mapped[str] = mapped_column(String(60))
    period_type: Mapped[str] = mapped_column(String(10))  # DAILY | WEEKLY | MONTHLY
    period_key: Mapped[str] = mapped_column(String(12))
    status: Mapped[ChallengeStatus] = mapped_column(
        Enum(ChallengeStatus), default=ChallengeStatus.ACTIVE
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class MemberRole(str, enum.Enum):
    MANAGER = "MANAGER"
    MEMBER = "MEMBER"
    VIEWER = "VIEWER"


class PortfolioMember(Base):
    """Cooperative portfolios (roadmap 7.2): additional users with a role.
    Managers and members vote on trade proposals; viewers watch."""

    __tablename__ = "portfolio_members"
    __table_args__ = (
        Index("ix_portfolio_member_unique", "portfolio_id", "username", unique=True),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    portfolio_id: Mapped[str] = mapped_column(ForeignKey("portfolios.id", ondelete="CASCADE"))
    username: Mapped[str] = mapped_column(String(80))
    role: Mapped[MemberRole] = mapped_column(Enum(MemberRole), default=MemberRole.MEMBER)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ProposalStatus(str, enum.Enum):
    OPEN = "OPEN"
    EXECUTED = "EXECUTED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"


class TradeProposal(Base):
    """Shared-decision trading (roadmap 7.2): a proposed market order that
    executes automatically once a majority of voters approve."""

    __tablename__ = "trade_proposals"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    portfolio_id: Mapped[str] = mapped_column(ForeignKey("portfolios.id", ondelete="CASCADE"))
    proposer: Mapped[str] = mapped_column(String(80))
    symbol: Mapped[str] = mapped_column(String(20))
    side: Mapped[OrderSide] = mapped_column(Enum(OrderSide))
    quantity: Mapped[Decimal | None] = mapped_column(DecimalStr, nullable=True)
    notional: Mapped[Decimal | None] = mapped_column(DecimalStr, nullable=True)
    rationale: Mapped[str] = mapped_column(Text, default="")
    votes: Mapped[str] = mapped_column(Text, default="{}")  # {username: true/false}
    status: Mapped[ProposalStatus] = mapped_column(
        Enum(ProposalStatus), default=ProposalStatus.OPEN
    )
    detail: Mapped[str] = mapped_column(Text, default="")
    executed_order_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CompetitionKind(str, enum.Enum):
    PUBLIC = "PUBLIC"
    PRIVATE = "PRIVATE"  # invite code — also covers friend/classroom games


class CompetitionScoring(str, enum.Enum):
    RETURN = "RETURN"
    RISK_ADJUSTED = "RISK_ADJUSTED"
    DIVERSIFICATION = "DIVERSIFICATION"


class Competition(Base):
    """Multiplayer games (roadmap 7.1-7.2): every entrant gets a fresh game
    portfolio with the same starting balance; standings rank by the chosen
    scoring."""

    __tablename__ = "competitions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")
    kind: Mapped[CompetitionKind] = mapped_column(
        Enum(CompetitionKind), default=CompetitionKind.PUBLIC
    )
    scoring: Mapped[CompetitionScoring] = mapped_column(
        Enum(CompetitionScoring), default=CompetitionScoring.RETURN
    )
    starting_balance: Mapped[Decimal] = mapped_column(DecimalStr, default=Decimal("100000"))
    invite_code: Mapped[str] = mapped_column(String(12), default="")
    created_by: Mapped[str] = mapped_column(String(80), default="local")
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CompetitionEntry(Base):
    __tablename__ = "competition_entries"
    __table_args__ = (
        Index("ix_competition_entry_unique", "competition_id", "username", unique=True),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    competition_id: Mapped[str] = mapped_column(
        ForeignKey("competitions.id", ondelete="CASCADE")
    )
    portfolio_id: Mapped[str] = mapped_column(ForeignKey("portfolios.id", ondelete="CASCADE"))
    username: Mapped[str] = mapped_column(String(80))
    display_name: Mapped[str] = mapped_column(String(80), default="")
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Club(Base):
    """Investment clubs (roadmap 7.4)."""

    __tablename__ = "clubs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")
    invite_code: Mapped[str] = mapped_column(String(12))
    created_by: Mapped[str] = mapped_column(String(80), default="local")
    club_portfolio_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ClubMember(Base):
    __tablename__ = "club_members"
    __table_args__ = (Index("ix_club_member_unique", "club_id", "username", unique=True),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    club_id: Mapped[str] = mapped_column(ForeignKey("clubs.id", ondelete="CASCADE"))
    username: Mapped[str] = mapped_column(String(80))
    role: Mapped[MemberRole] = mapped_column(Enum(MemberRole), default=MemberRole.MEMBER)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ClubMessage(Base):
    __tablename__ = "club_messages"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    club_id: Mapped[str] = mapped_column(ForeignKey("clubs.id", ondelete="CASCADE"))
    author: Mapped[str] = mapped_column(String(80))
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ShareLink(Base):
    """Read-only sharing (roadmap 7.6): random-token URLs exposing a
    portfolio snapshot or a strategy definition, revocable."""

    __tablename__ = "share_links"

    token: Mapped[str] = mapped_column(String(48), primary_key=True)
    kind: Mapped[str] = mapped_column(String(16))  # portfolio | strategy
    target_id: Mapped[str] = mapped_column(String(32))
    created_by: Mapped[str] = mapped_column(String(80), default="local")
    revoked: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AppSetting(Base):
    """Small global key/value store (e.g. default AI model)."""

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")


class RuleActionType(str, enum.Enum):
    BUY = "BUY"
    SELL = "SELL"
    REBALANCE = "REBALANCE"
    NOTIFY = "NOTIFY"


class AutomationRule(Base):
    """User-defined automation: a JSON trigger AST plus one action. Evaluated
    event-driven on price updates and on a schedule tick; never eval()'d code
    (ARCHITECTURE.md §5)."""

    __tablename__ = "automation_rules"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    portfolio_id: Mapped[str] = mapped_column(ForeignKey("portfolios.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(120))
    trigger: Mapped[str] = mapped_column(Text)  # JSON AST
    action_type: Mapped[RuleActionType] = mapped_column(Enum(RuleActionType))
    action_params: Mapped[str] = mapped_column(Text, default="{}")  # JSON
    enabled: Mapped[bool] = mapped_column(default=True)
    cooldown_seconds: Mapped[int] = mapped_column(default=3600)
    max_fires_per_day: Mapped[int] = mapped_column(default=5)
    # M11: one-shot rules disable themselves after their first fire
    fire_once: Mapped[bool] = mapped_column(default=False)
    last_fired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fire_count: Mapped[int] = mapped_column(default=0)
    armed: Mapped[bool] = mapped_column(default=True)  # edge-trigger state: re-arms when condition goes false
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    fires: Mapped[list["RuleFire"]] = relationship(
        back_populates="rule", cascade="all, delete-orphan", order_by="RuleFire.fired_at.desc()"
    )


class RuleFire(Base):
    __tablename__ = "rule_fires"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    rule_id: Mapped[str] = mapped_column(ForeignKey("automation_rules.id", ondelete="CASCADE"))
    fired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    result: Mapped[str] = mapped_column(String(20))  # EXECUTED | NOTIFIED | REJECTED | ERROR
    detail: Mapped[str] = mapped_column(Text, default="")

    rule: Mapped[AutomationRule] = relationship(back_populates="fires")


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    type: Mapped[str] = mapped_column(String(40))  # order_filled | rule_fired | dividend | ...
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text, default="")
    portfolio_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    read: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class User(Base):
    """Server-mode account. M3 supports a single admin; roles/multi-user in M6."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    username: Mapped[str] = mapped_column(String(80), unique=True)
    password_hash: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(20), default="admin")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuthSession(Base):
    __tablename__ = "auth_sessions"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ProviderCredential(Base):
    """Encrypted-at-rest provider API keys (PRD §27). Values are Fernet
    ciphertext; the key file lives in the data directory with 0600 perms."""

    __tablename__ = "provider_credentials"

    provider: Mapped[str] = mapped_column(String(40), primary_key=True)
    encrypted_value: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    actor: Mapped[str] = mapped_column(String(80), default="local")
    action: Mapped[str] = mapped_column(String(80))
    entity: Mapped[str] = mapped_column(String(200), default="")
    detail: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AppliedCorporateAction(Base):
    """Idempotency record: which dividend/split events have already been
    applied to which portfolio."""

    __tablename__ = "applied_corporate_actions"
    __table_args__ = (
        Index(
            "ix_applied_corp_unique", "portfolio_id", "symbol", "kind", "ex_ts", unique=True
        ),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    portfolio_id: Mapped[str] = mapped_column(ForeignKey("portfolios.id", ondelete="CASCADE"))
    symbol: Mapped[str] = mapped_column(String(20))
    kind: Mapped[str] = mapped_column(String(16))  # DIVIDEND | SPLIT
    ex_ts: Mapped[int] = mapped_column()  # provider event timestamp (unix)
    applied_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# ---------------------------------------------------------------- M8 models


class ObservationStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    RESOLVED = "RESOLVED"


class MentorObservation(Base):
    """Persistent mentor memory (roadmap 8.1): one row per (user, insight
    code), updated each analysis run. RESOLVED rows are kept — the mentor
    remembers what you fixed."""

    __tablename__ = "mentor_observations"
    __table_args__ = (Index("ix_mentor_obs_unique", "username", "code", unique=True),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    username: Mapped[str] = mapped_column(String(80), default="local")
    code: Mapped[str] = mapped_column(String(60))
    category: Mapped[str] = mapped_column(String(20))  # behavior|allocation|knowledge|strength
    severity: Mapped[str] = mapped_column(String(12), default="info")  # info|notice|important
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text, default="")
    evidence: Mapped[str] = mapped_column(Text, default="{}")  # JSON metrics backing it
    status: Mapped[ObservationStatus] = mapped_column(
        Enum(ObservationStatus), default=ObservationStatus.ACTIVE
    )
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    times_seen: Mapped[int] = mapped_column(default=1)


class MentorProfile(Base):
    """The mentor's model of the investor (roadmap 8.1): style, traits,
    strengths, and knowledge gaps, refreshed by the analysis engine."""

    __tablename__ = "mentor_profiles"

    username: Mapped[str] = mapped_column(String(80), primary_key=True)
    style: Mapped[str] = mapped_column(String(60), default="")
    traits: Mapped[str] = mapped_column(Text, default="{}")  # JSON metric snapshot
    strengths: Mapped[str] = mapped_column(Text, default="[]")  # JSON list
    knowledge_gaps: Mapped[str] = mapped_column(Text, default="[]")  # JSON list
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ScenarioSession(Base):
    """A historical replay in progress (roadmap 8.2). The virtual clock only
    moves forward; the API never serves bars beyond current_ts, so the player
    has no future knowledge. value_points accumulates the player's daily
    value series for the comparison chart."""

    __tablename__ = "scenario_sessions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    scenario_id: Mapped[str] = mapped_column(String(40))
    username: Mapped[str] = mapped_column(String(80), default="local")
    display_name: Mapped[str] = mapped_column(String(80), default="")
    portfolio_id: Mapped[str] = mapped_column(ForeignKey("portfolios.id", ondelete="CASCADE"))
    current_ts: Mapped[int] = mapped_column()  # unix ts of the virtual "today" bar
    completed: Mapped[bool] = mapped_column(default=False)
    value_points: Mapped[str] = mapped_column(Text, default="[]")  # JSON [(ts, value)]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CareerState(Base):
    """Career-mode progression (roadmap 8.3): rank index plus the objective
    codes completed so far (append-only; objectives never un-complete)."""

    __tablename__ = "career_states"

    username: Mapped[str] = mapped_column(String(80), primary_key=True)
    rank: Mapped[int] = mapped_column(default=0)
    completed: Mapped[str] = mapped_column(Text, default="[]")  # JSON list of codes
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Classroom(Base):
    """Classroom mode (roadmap 8.6): an instructor and their students."""

    __tablename__ = "classrooms"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(120))
    instructor: Mapped[str] = mapped_column(String(80))
    invite_code: Mapped[str] = mapped_column(String(12))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ClassroomStudent(Base):
    __tablename__ = "classroom_students"
    __table_args__ = (
        Index("ix_classroom_student_unique", "classroom_id", "username", unique=True),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    classroom_id: Mapped[str] = mapped_column(ForeignKey("classrooms.id", ondelete="CASCADE"))
    username: Mapped[str] = mapped_column(String(80))
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Assignment(Base):
    """Instructor-created work (roadmap 8.6): a fresh portfolio per student,
    optionally pinned to a historical scenario and/or a mandate."""

    __tablename__ = "assignments"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    classroom_id: Mapped[str] = mapped_column(ForeignKey("classrooms.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    scenario_id: Mapped[str] = mapped_column(String(40), default="")  # "" = live market
    mandate: Mapped[str] = mapped_column(String(20), default="")
    starting_balance: Mapped[Decimal] = mapped_column(DecimalStr, default=Decimal("100000"))
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AssignmentEntry(Base):
    """A student's started assignment: links to their working portfolio (and
    scenario session when the assignment replays history)."""

    __tablename__ = "assignment_entries"
    __table_args__ = (
        Index("ix_assignment_entry_unique", "assignment_id", "username", unique=True),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    assignment_id: Mapped[str] = mapped_column(ForeignKey("assignments.id", ondelete="CASCADE"))
    username: Mapped[str] = mapped_column(String(80))
    portfolio_id: Mapped[str] = mapped_column(ForeignKey("portfolios.id", ondelete="CASCADE"))
    scenario_session_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# ---------------------------------------------------------------- M9 models


class AiPlayer(Base):
    """A simulated opponent (roadmap 9.1-9.4): an investing philosophy plus
    a personality (traits scaled by difficulty) driving a real portfolio.
    All of its trades carry origin=AI_AUTO — permanently marked."""

    __tablename__ = "ai_players"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    competition_id: Mapped[str] = mapped_column(
        ForeignKey("competitions.id", ondelete="CASCADE"))
    portfolio_id: Mapped[str] = mapped_column(
        ForeignKey("portfolios.id", ondelete="CASCADE"))
    profile: Mapped[str] = mapped_column(String(20))
    difficulty: Mapped[str] = mapped_column(String(15), default="intermediate")
    display_name: Mapped[str] = mapped_column(String(80))
    traits: Mapped[str] = mapped_column(Text, default="{}")  # JSON personality
    adaptive: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_cycle_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True)


class AiDecision(Base):
    """Full transparency (roadmap 9.5): every AI action — including HOLD —
    with its reason, the data consulted, confidence, and expected outcome."""

    __tablename__ = "ai_decisions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    ai_player_id: Mapped[str] = mapped_column(
        ForeignKey("ai_players.id", ondelete="CASCADE"))
    action: Mapped[str] = mapped_column(String(12))  # BUY|SELL|HOLD|MISTAKE
    symbol: Mapped[str] = mapped_column(String(20), default="")
    reason: Mapped[str] = mapped_column(Text, default="")
    data_used: Mapped[str] = mapped_column(Text, default="{}")  # JSON
    confidence: Mapped[int] = mapped_column(default=50)  # 0-100
    expected_outcome: Mapped[str] = mapped_column(Text, default="")
    executed_order_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ConceptProgress(Base):
    """Knowledge tracking (roadmap 10.7): per-user record of concepts
    viewed and quiz results."""

    __tablename__ = "concept_progress"
    __table_args__ = (
        Index("ix_concept_progress_unique", "username", "concept_id", unique=True),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    username: Mapped[str] = mapped_column(String(80), default="local")
    concept_id: Mapped[str] = mapped_column(String(60))
    viewed_count: Mapped[int] = mapped_column(default=0)
    quiz_score: Mapped[int | None] = mapped_column(nullable=True)  # percent
    quiz_passed: Mapped[bool] = mapped_column(default=False)
    first_viewed: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_viewed: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Game(Base):
    """M11: an isolated space grouping portfolios (e.g. 'Long-term ideas'
    vs 'YOLO experiments'). Filtering, not a hard wall — profile/XP stay
    global."""

    __tablename__ = "games"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    owner: Mapped[str] = mapped_column(String(80), default="local")
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class FutureSession(Base):
    """Future game mode (M11 note 11): time runs as fast as you want,
    forward from today's REAL prices, along SIMULATED paths statistically
    calibrated to each stock's real history. Every surface that shows these
    prices labels them simulated — they are practice fiction, not forecasts."""

    __tablename__ = "future_sessions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    username: Mapped[str] = mapped_column(String(80), default="local")
    portfolio_id: Mapped[str] = mapped_column(ForeignKey("portfolios.id", ondelete="CASCADE"))
    seed: Mapped[str] = mapped_column(String(32))
    symbols: Mapped[str] = mapped_column(Text)  # JSON list
    calibration: Mapped[str] = mapped_column(Text, default="{}")  # JSON per-symbol {p0, mu, sigma}
    current_step: Mapped[int] = mapped_column(default=0)  # trading days into the future
    value_points: Mapped[str] = mapped_column(Text, default="[]")  # JSON [(step, value)]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
