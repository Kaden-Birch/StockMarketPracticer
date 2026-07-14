const BASE = "/api/v1";

export interface HoldingView {
  symbol: string;
  quantity: string;
  avg_cost: string | null;
  cost_basis: string;
  price: string | null;
  market_value: string | null;
  unrealized_pnl: string | null;
  day_change: string | null;
  quote_as_of: string | null;
  provider: string | null;
}

export interface PortfolioView {
  id: string;
  name: string;
  description: string;
  currency: string;
  starting_balance: string;
  cash_balance: string;
  cost_basis_method: string;
  dividend_reinvest: boolean;
  mode: string;
  owner: string;
  public_on_leaderboard: boolean;
  game_xp: number;
  game_id: string | null;
  created_at: string;
  holdings: HoldingView[];
  market_value: string;
  total_value: string;
  total_cost_basis: string;
  unrealized_pnl: string;
  day_change: string;
  lifetime_return: string;
  quote_errors: string[];
}

export interface Order {
  id: string;
  portfolio_id: string;
  symbol: string;
  side: "BUY" | "SELL";
  type: "MARKET" | "LIMIT" | "STOP" | "STOP_LIMIT" | "TRAILING_STOP";
  quantity: string | null;
  notional: string | null;
  percent: string | null;
  percent_of: string | null;
  limit_price: string | null;
  stop_price: string | null;
  trail_amount: string | null;
  trail_percent: string | null;
  watermark: string | null;
  status: "PENDING" | "FILLED" | "CANCELLED" | "REJECTED";
  reject_reason: string;
  origin: string;
  created_at: string;
  filled_at: string | null;
}

export interface Txn {
  id: string;
  symbol: string;
  side: "BUY" | "SELL";
  quantity: string;
  price: string;
  amount: string;
  realized_pnl: string | null;
  kind: "TRADE" | "DIVIDEND" | "SPLIT";
  fx_rate: string;
  quote_currency: string;
  origin: string;
  executed_at: string;
}

export interface RecurringPlan {
  id: string;
  portfolio_id: string;
  symbol: string;
  amount: string;
  cadence: "DAILY" | "WEEKLY" | "MONTHLY";
  next_run_at: string;
  enabled: boolean;
  last_run_at: string | null;
  run_count: number;
}

export interface WatchlistView {
  id: string;
  name: string;
  items: {
    symbol: string;
    price: string | null;
    previous_close: string | null;
    change: string | null;
    change_pct: string | null;
    currency: string | null;
    provider: string | null;
  }[];
  quote_errors: string[];
}

export interface RebalancePlan {
  total_value: string;
  cash_balance: string;
  current_weights: Record<string, string>;
  targets: Record<string, string>;
  trades: { symbol: string; side: string; quantity?: string; notional?: string; est_value: string }[];
}

export interface ValueHistory {
  portfolio_id: string;
  range: string;
  currency: string;
  benchmark: string;
  points: { date: string; value: number; benchmark_close: number }[];
}

export interface Analytics {
  portfolio_id: string;
  range: string;
  risk: {
    volatility: number | null;
    sharpe: number | null;
    sortino: number | null;
    beta: number | null;
    max_drawdown: number | null;
    error?: string;
  };
  records: {
    realized_by_symbol: Record<string, string>;
    best_symbol: { symbol: string; realized_pnl: string } | null;
    worst_symbol: { symbol: string; realized_pnl: string } | null;
    largest_gain: { symbol: string; realized_pnl: string; executed_at: string } | null;
    largest_loss: { symbol: string; realized_pnl: string; executed_at: string } | null;
    win_rate: number | null;
    closed_trades: number;
    avg_trip_return: number | null;
    avg_holding_days: number | null;
  };
  diversification: { score: number | null; weights: Record<string, number> };
}

export interface AutomationRuleView {
  id: string;
  portfolio_id: string;
  name: string;
  trigger: object;
  action_type: "BUY" | "SELL" | "REBALANCE" | "NOTIFY";
  action_params: Record<string, unknown>;
  enabled: boolean;
  cooldown_seconds: number;
  max_fires_per_day: number;
  fire_once: boolean;
  last_fired_at: string | null;
  fire_count: number;
  created_at: string;
}

export interface RuleFireView {
  id: string;
  fired_at: string;
  result: string;
  detail: string;
}

export interface NotificationView {
  id: string;
  type: string;
  title: string;
  body: string;
  portfolio_id: string | null;
  read: boolean;
  created_at: string;
}

export interface AuthStatus {
  mode: "disabled" | "required";
  state: "authenticated" | "setup_required" | "login_required";
  username?: string;
}

export interface ModelView {
  id: string;
  name: string;
  version: string;
  parameters: string;
  quantization: string;
  disk_gb: number;
  min_ram_gb: number;
  recommended_ram_gb: number;
  gpu_vram_gb: number;
  est_speed: string;
  features: string[];
  installed: boolean;
  loaded: boolean;
  hardware_fit: "fits" | "marginal" | "too_large" | "unknown";
  download: { done: number; total: number; speed_bps?: number } | null;
}

export interface RecommendationView {
  id: string;
  model_id: string;
  action: "BUY" | "SELL" | "HOLD";
  symbol: string;
  sizing: { notional?: string };
  rationale: string;
  confidence: string | null;
  analysis: string;
  expected_impact: Record<string, string | null>;
  status: "PENDING" | "APPROVED" | "REJECTED" | "EXPIRED" | "EXECUTED";
  executed_order_id: string | null;
  created_at: string;
  decided_at: string | null;
}

export interface AiSettings {
  ai_auto_execute: boolean;
  ai_max_trade_notional: string;
  ai_max_trades_per_day: number;
  ai_default_model: string;
}

export interface StrategyView {
  id: string;
  name: string;
  description: string;
  universe: string[];
  entry_trigger: object;
  exit_trigger: object | null;
  entry_notional: string;
  initial_cash: string;
  benchmark: string;
  created_at: string;
}

export interface BacktestResults {
  days: number;
  initial_cash: string;
  final_value: number;
  total_return_pct: number;
  benchmark: string;
  benchmark_return_pct: number;
  trades: number;
  closed_trades: number;
  wins: number;
  losses: number;
  win_rate: number | null;
  realized_pnl: string;
  risk: { sharpe: number | null; sortino: number | null; beta: number | null;
          volatility: number | null; max_drawdown: number | null };
  by_regime: Record<string, { days: number; total_return_pct: number | null }>;
  open_positions: { symbol: string; quantity: string; value: string }[];
  trade_log: { date: string; side: string; symbol: string; quantity: string;
               price: string; realized_pnl?: string }[];
  equity_curve: { date: string; value: number; benchmark_close: number }[];
}

export interface BacktestRunView {
  id: string;
  strategy_id: string;
  range: string;
  status: "RUNNING" | "DONE" | "FAILED";
  progress_pct: number;
  error: string;
  results: BacktestResults | Record<string, never>;
  created_at: string;
  finished_at: string | null;
}

export interface WhatIfResult {
  description: string;
  range: string;
  currency: string;
  actual_final: number;
  hypothetical_final: number;
  delta: number;
  delta_pct: number | null;
  actual_points: { date: string; value: number }[];
  hypothetical_points: { date: string; value: number }[];
  note: string;
}

export interface GamifyProfile {
  username: string;
  avatar: string;
  gamification_enabled: boolean;
  progress: {
    level: number;
    title: string;
    xp: number;
    level_floor_xp: number;
    next_level_xp: number;
    progress_pct: number;
    titles: { level: number; title: string; earned: boolean }[];
  };
  xp_by_category: Record<string, number>;
  achievements: {
    id: string; name: string; category: string; description: string;
    xp: number; earned_at: string | null;
  }[];
  recent_xp: { category: string; kind: string; amount: number; reason: string;
               created_at: string }[];
}

export interface ChallengeView {
  id: string;
  challenge_id: string;
  name: string;
  description: string;
  period_type: "DAILY" | "WEEKLY" | "MONTHLY";
  period_key: string;
  current: boolean;
  xp: number;
  status: "ACTIVE" | "COMPLETED";
  completed_at: string | null;
}

export interface ReportCard {
  overall: string;
  generated_at: string;
  subjects: Record<string, { grade: string; detail: string }>;
  note: string;
}

export interface CoachObservation {
  id: string;
  observation: string;
  suggestion: string;
  topic: string;
  disclaimer: string;
}

export interface ModuleView {
  id: string;
  name: string;
  version: string;
  description: string;
  dependencies: string[];
  permissions: string[];
  events_published: string[];
  events_consumed: string[];
  ui: { kind: string; label: string; path: string; icon: string }[];
  state: "RUNNING" | "DISABLED" | "FAILED" | "REGISTERED";
  disabled_reason: string | null;
  error: string | null;
  pending_change: string | null;
}

export interface PresetView {
  id: string;
  label: string;
  description: string;
  disabled_modules: string[];
}

export interface CompareSeries {
  symbol: string;
  currency: string;
  provider: string;
  points: { ts: number; value: number }[];
  total_return_pct: number | null;
  volatility_pct: number | null;
}

export interface QuoteView {
  symbol: string;
  price: string;
  previous_close: string | null;
  currency: string;
  market_state: string;
  as_of: string;
  provider: string;
}

export interface HistoryBar {
  ts: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number | null;
}

export interface HistoryView {
  symbol: string;
  range: string;
  interval: string;
  currency: string;
  provider: string;
  bars: HistoryBar[];
}

export interface SymbolMatch {
  symbol: string;
  name: string;
  exchange: string;
  type: string;
}

export interface CompetitionView {
  id: string;
  name: string;
  description: string;
  kind: "PUBLIC" | "PRIVATE";
  scoring: "RETURN" | "RISK_ADJUSTED" | "DIVERSIFICATION";
  starting_balance: string;
  created_by: string;
  entries: number;
  joined: boolean;
  invite_code?: string;
  ends_at: string | null;
  created_at: string;
}

export interface StandingRow {
  rank: number;
  display_name: string;
  score: number | null;
  return_pct: number | null;
  total_value: string;
  is_me: boolean;
  is_ai?: boolean;
  ai_player_id?: string;
}

export interface AiProfileInfo {
  id: string;
  name: string;
  philosophy: string;
  universe: string[];
  method: string;
  traits: Record<string, number>;
  difficulties: string[];
}

export interface AiPlayerView {
  id: string;
  profile: string;
  name: string;
  philosophy: string;
  difficulty: string;
  adaptive: boolean;
  traits: Record<string, number>;
  portfolio_id: string;
  value?: string | null;
  return_pct?: string;
  holdings?: { symbol: string; market_value: string | null }[];
  last_cycle_at: string | null;
}

export interface AiDecisionView {
  action: string;
  symbol: string;
  reason: string;
  data_used: Record<string, unknown>;
  confidence: number;
  expected_outcome: string;
  executed_order_id: string | null;
  created_at: string;
}

export interface TournamentInfo {
  id: string;
  name: string;
  description: string;
  ai_players: { profile: string; difficulty: string; adaptive: boolean }[];
}

export interface CompetitionAnalysis {
  standings: {
    rank: number; name: string; is_you: boolean; is_ai: boolean;
    return_pct: number; trades: number; win_rate: number | null;
    diversification: number | null; cash_pct: number | null;
  }[];
  findings: string[];
}

export interface MemberView {
  username: string;
  role: "MANAGER" | "MEMBER" | "VIEWER";
  added_at?: string;
}

export interface ProposalView {
  id: string;
  proposer: string;
  symbol: string;
  side: "BUY" | "SELL";
  quantity: string | null;
  notional: string | null;
  rationale: string;
  status: "OPEN" | "EXECUTED" | "REJECTED" | "FAILED";
  detail: string;
  votes: Record<string, boolean>;
  approvals: number;
  rejections: number;
  eligible_voters: number;
  executed_order_id: string | null;
  created_at: string;
}

export interface ClubSummary {
  id: string;
  name: string;
  description: string;
  club_portfolio_id: string | null;
  created_at: string;
}

export interface ClubView extends ClubSummary {
  created_by: string;
  invite_code?: string;
  members: MemberView[];
}

export interface ClubMessageView {
  id: string;
  author: string;
  body: string;
  created_at: string;
}

export interface ClubRankRow {
  rank: number;
  username: string;
  role: string;
  best_return_pct: number | null;
}

export interface ShareLinkView {
  token: string;
  kind: "portfolio" | "strategy";
  target_id: string;
  revoked: boolean;
  created_at: string;
}

export interface SharedPortfolioView {
  kind: "portfolio";
  name: string;
  currency: string;
  mode: string;
  created_at: string;
  starting_balance: string;
  total_value: string;
  lifetime_return: string;
  total_return_pct: string | null;
  day_change: string;
  holdings: { symbol: string; quantity: string; market_value: string | null }[];
}

export interface SharedStrategyView {
  kind: "strategy";
  name: string;
  description: string;
  universe: string[];
  entry_trigger: object;
  exit_trigger: object | null;
  entry_notional: string;
  benchmark: string;
}

export interface LeaderboardEntry {
  rank: number;
  portfolio: string;
  owner: string;
  mode: string;
  score: number;
  label: string;
  is_me: boolean;
}

export interface LeaderboardCategory {
  id: string;
  name: string;
  entries: LeaderboardEntry[];
}

export interface DiscordConfigView {
  webhook_configured: boolean;
  bot_token_configured: boolean;
  gateway_available: boolean;
  events: string[];
  available_events: string[];
  commands: Record<string, string>;
}

export interface UserView {
  username: string;
  role: string;
  created_at: string;
}

// ---- M8: mentor, scenarios, career, classroom ----

export interface MentorObservationView {
  id: string;
  code: string;
  category: string;
  severity: "info" | "notice" | "important";
  title: string;
  body: string;
  evidence: Record<string, unknown>;
  status: "ACTIVE" | "ACKNOWLEDGED" | "RESOLVED";
  first_seen: string;
  times_seen: number;
}

export interface MentorView {
  profile: {
    style: string;
    traits: Record<string, unknown>;
    strengths: string[];
    knowledge_gaps: string[];
    updated_at: string | null;
  };
  observations: MentorObservationView[];
  resolved: MentorObservationView[];
}

export interface ScenarioInfo {
  id: string;
  name: string;
  period: string;
  description: string;
  benchmark: string;
  universe: string[];
  starting_cash: string;
  difficulty: string;
}

export interface ScenarioSessionView {
  id: string;
  scenario: ScenarioInfo;
  portfolio_id: string;
  display_name: string;
  virtual_date: string;
  day: number;
  total_days: number;
  completed: boolean;
  cash: string;
  value: string;
  return_pct: string;
  market_return_pct: string;
  quotes: Record<string, { price: string | null; prev_close: string | null; listed: boolean }>;
  holdings: { symbol: string; quantity: string; price: string | null; market_value: string | null }[];
}

export interface ScenarioComparison {
  series: { id: string; name: string; points: [number, string][] }[];
  players: { display_name: string; day: number; value: string; return_pct: string; completed: boolean }[];
}

export interface CareerObjective {
  code: string;
  rank: number;
  rank_name: string;
  label: string;
  description: string;
  done: boolean;
  current: boolean;
}

export interface CareerView {
  rank: number;
  rank_name: string;
  next_rank: string | null;
  ladder: string[];
  objectives: CareerObjective[];
  challenges: CareerObjective[];
  progress?: { trades: number; total_value: string; best_diversification: number | null };
}

export interface MandateRule {
  id: string;
  label: string;
  status: "ok" | "violation" | "pending";
  value: unknown;
  threshold: string;
}

export interface MandateCompliance {
  mandate: string;
  info?: { name: string; summary: string };
  rules: MandateRule[];
  compliant: boolean | null;
}

export interface ClassroomView {
  id: string;
  name: string;
  instructor: string;
  role?: string;
  is_instructor?: boolean;
  invite_code?: string;
  students?: { username: string; joined_at: string }[];
  created_at?: string;
}

export interface AssignmentView {
  id: string;
  classroom_id: string;
  title: string;
  description: string;
  scenario_id: string;
  mandate: string;
  starting_balance: string;
  due_at: string | null;
  my_entry: { portfolio_id: string; scenario_session_id: string | null; started_at: string } | null;
}

export interface ClassroomProgress {
  classroom: string;
  progress: {
    assignment: Omit<AssignmentView, "my_entry">;
    students: {
      username: string; started: boolean; value?: string; return_pct?: string;
      scenario_day?: number; scenario_total_days?: number; completed?: boolean;
      mandate_compliant?: boolean | null; note?: string;
    }[];
  }[];
}

// ---- M10: knowledge base ----

export interface ConceptSummary {
  id: string;
  term: string;
  category: string;
  category_name: string;
  beginner: string;
  intermediate: string;
  advanced: string;
  related: string[];
  has_quiz: boolean;
  viewed?: boolean;
  quiz_passed?: boolean;
}

export interface ConceptDetail extends ConceptSummary {
  quiz?: { question: string; options: string[] }[];
  viewed_count: number;
  quiz_score: number | null;
}

export interface QuizResult {
  score: number;
  passed: boolean;
  results: { correct: boolean; answer: number; why: string }[];
}

export interface PathView {
  id: string;
  name: string;
  description: string;
  steps: { concept_id: string; term: string; viewed: boolean;
           has_quiz: boolean; quiz_passed: boolean; complete: boolean }[];
  done: number;
  total: number;
  completed: boolean;
}

export interface LearnProgress {
  concepts_viewed: number;
  concepts_total: number;
  quizzes_passed: number;
  paths_completed: string[];
  categories: Record<string, { name: string; viewed: number; total: number }>;
  achievements: { id: string; name: string; description: string; earned: boolean }[];
}

export interface LearnSuggestion {
  concept_id: string;
  term?: string;
  why: string;
  portfolio: string | null;
}

export interface FutureView {
  id: string;
  simulated: boolean;
  disclaimer: string;
  portfolio_id: string;
  symbols: string[];
  seed: string;
  step: number;
  virtual_date: string;
  years_elapsed: number;
  cash: string;
  value: string;
  return_pct: string;
  quotes: Record<
    string,
    { price: string; prev_close: string | null; start_price: string; simulated: boolean }
  >;
  holdings: { symbol: string; quantity: string; market_value: string }[];
  value_points: { step: number; date: string; value: string }[];
}

export class AuthRequiredError extends Error {}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    credentials: "same-origin",
    ...init,
  });
  if (resp.status === 401) {
    window.dispatchEvent(new Event("aiptp-auth-required"));
    throw new AuthRequiredError("Authentication required");
  }
  if (!resp.ok) {
    let detail = resp.statusText;
    try {
      const body = await resp.json();
      if (typeof body.detail === "string") detail = body.detail;
      else if (body.detail) detail = JSON.stringify(body.detail);
    } catch {
      /* keep statusText */
    }
    throw new Error(detail);
  }
  if (resp.status === 204) return undefined as T;
  return resp.json();
}

export const api = {
  listPortfolios: (game = "") =>
    request<PortfolioView[]>(`/portfolios${game ? `?game=${game}` : ""}`),
  getPortfolio: (id: string) => request<PortfolioView>(`/portfolios/${id}`),
  createPortfolio: (body: object) =>
    request<PortfolioView>("/portfolios", { method: "POST", body: JSON.stringify(body) }),
  deletePortfolio: (id: string) => request<void>(`/portfolios/${id}`, { method: "DELETE" }),
  listOrders: (pid: string) => request<Order[]>(`/portfolios/${pid}/orders`),
  placeOrder: (pid: string, body: object) =>
    request<Order>(`/portfolios/${pid}/orders`, { method: "POST", body: JSON.stringify(body) }),
  cancelOrder: (pid: string, oid: string) =>
    request<Order>(`/portfolios/${pid}/orders/${oid}`, { method: "DELETE" }),
  listTransactions: (pid: string) => request<Txn[]>(`/portfolios/${pid}/transactions`),
  quotes: (symbols: string[]) =>
    request<Record<string, QuoteView>>(`/marketdata/quotes?symbols=${symbols.join(",")}`),
  history: (symbol: string, range: string) =>
    request<HistoryView>(`/marketdata/history/${symbol}?range=${range}`),
  search: (q: string) => request<SymbolMatch[]>(`/marketdata/search?q=${encodeURIComponent(q)}`),
  compare: (symbols: string[], range: string) =>
    request<{ range: string; series: CompareSeries[] }>(
      `/marketdata/compare?symbols=${symbols.join(",")}&range=${range}`,
    ),
  symbolTransactions: (symbol: string) => request<Txn[]>(`/symbols/${symbol}/transactions`),
  placeBatch: (pid: string, orders: object[]) =>
    request<{ results: { symbol: string; status: string; error?: string }[] }>(
      `/portfolios/${pid}/orders/batch`,
      { method: "POST", body: JSON.stringify({ orders }) },
    ),
  rebalance: (pid: string, targets: Record<string, number>, execute: boolean) =>
    request<{ plan: RebalancePlan; executed: { symbol: string; status: string }[] | null }>(
      `/portfolios/${pid}/rebalance`,
      { method: "POST", body: JSON.stringify({ targets, execute }) },
    ),
  updatePortfolio: (pid: string, body: object) =>
    request<PortfolioView>(`/portfolios/${pid}`, { method: "PATCH", body: JSON.stringify(body) }),
  listPlans: (pid: string) => request<RecurringPlan[]>(`/portfolios/${pid}/plans`),
  createPlan: (pid: string, body: object) =>
    request<RecurringPlan>(`/portfolios/${pid}/plans`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  updatePlan: (pid: string, planId: string, body: object) =>
    request<RecurringPlan>(`/portfolios/${pid}/plans/${planId}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  deletePlan: (pid: string, planId: string) =>
    request<void>(`/portfolios/${pid}/plans/${planId}`, { method: "DELETE" }),
  listWatchlists: () => request<WatchlistView[]>("/watchlists"),
  createWatchlist: (name: string) =>
    request<WatchlistView>("/watchlists", { method: "POST", body: JSON.stringify({ name }) }),
  deleteWatchlist: (id: string) => request<void>(`/watchlists/${id}`, { method: "DELETE" }),
  addWatchlistItem: (id: string, symbol: string) =>
    request<WatchlistView>(`/watchlists/${id}/items`, {
      method: "POST",
      body: JSON.stringify({ symbol }),
    }),
  removeWatchlistItem: (id: string, symbol: string) =>
    request<void>(`/watchlists/${id}/items/${symbol}`, { method: "DELETE" }),
  valueHistory: (pid: string, range: string) =>
    request<ValueHistory>(`/portfolios/${pid}/value-history?range=${range}`),
  analytics: (pid: string, range: string) =>
    request<Analytics>(`/portfolios/${pid}/analytics?range=${range}`),
  exportUrl: (pid: string, format: string) => `${BASE}/portfolios/${pid}/export?format=${format}`,
  listRules: (pid: string) => request<AutomationRuleView[]>(`/portfolios/${pid}/rules`),
  createRule: (pid: string, body: object) =>
    request<AutomationRuleView>(`/portfolios/${pid}/rules`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  updateRule: (pid: string, ruleId: string, body: object) =>
    request<AutomationRuleView>(`/portfolios/${pid}/rules/${ruleId}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  deleteRule: (pid: string, ruleId: string) =>
    request<void>(`/portfolios/${pid}/rules/${ruleId}`, { method: "DELETE" }),
  ruleFires: (pid: string, ruleId: string) =>
    request<RuleFireView[]>(`/portfolios/${pid}/rules/${ruleId}/fires`),
  notifications: (unreadOnly = false) =>
    request<{ unread_count: number; notifications: NotificationView[] }>(
      `/notifications?unread_only=${unreadOnly}`,
    ),
  markNotificationsRead: (ids?: string[]) =>
    request<{ ok: boolean }>("/notifications/read", {
      method: "POST",
      body: JSON.stringify(ids ?? null),
    }),
  authStatus: () => request<AuthStatus>("/auth/status"),
  authSetup: (username: string, password: string) =>
    request<{ username: string }>("/auth/setup", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    }),
  authLogin: (username: string, password: string) =>
    request<{ username: string }>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    }),
  authLogout: () => request<{ ok: boolean }>("/auth/logout", { method: "POST" }),
  adminProviders: () =>
    request<{ stored_keys: string[]; active_chain: string[]; supported: string[] }>(
      "/admin/providers",
    ),
  setProviderKey: (provider: string, key: string) =>
    request<{ ok: boolean; note: string }>("/admin/providers", {
      method: "PUT",
      body: JSON.stringify({ provider, key }),
    }),
  deleteProviderKey: (provider: string) =>
    request<void>(`/admin/providers/${provider}`, { method: "DELETE" }),
  runBackup: () => request<{ backup: string }>("/admin/backup", { method: "POST" }),
  listBackups: () =>
    request<{ name: string; size_bytes: number; created_at: string }[]>("/admin/backups"),
  auditLog: () =>
    request<{ actor: string; action: string; entity: string; detail: string; created_at: string }[]>(
      "/admin/audit",
    ),
  aiHardware: () =>
    request<{ cpu_count: number; ram_gb: number | null; gpus: { name: string; vram: string }[];
              runtime_available: boolean; runtime_kind: string }>("/ai/hardware"),
  aiModels: () =>
    request<{ models: ModelView[]; loaded: string | null; default_model: string;
              disclaimer: string }>("/ai/models"),
  aiInstall: (modelId: string) =>
    request<{ status: string }>(`/ai/models/${modelId}/install`, { method: "POST" }),
  aiRemove: (modelId: string) => request<void>(`/ai/models/${modelId}`, { method: "DELETE" }),
  aiLoad: (modelId: string) =>
    request<{ loaded: string }>(`/ai/models/${modelId}/load`, { method: "POST" }),
  aiBenchmark: (modelId: string) =>
    request<{ elapsed_seconds: number; completion_tokens: number;
              tokens_per_second: number | null }>(`/ai/models/${modelId}/benchmark`, {
      method: "POST",
    }),
  aiSetDefault: (modelId: string) =>
    request<{ default_model: string }>("/ai/default-model", {
      method: "PUT",
      body: JSON.stringify({ model_id: modelId }),
    }),
  aiAnalyze: (pid: string, modelId?: string) =>
    request<{ model_id: string; analysis: string; disclaimer: string;
              recommendations: RecommendationView[]; dropped_ungrounded: number;
              auto_executed: { status: string; reason?: string }[] }>(
      `/portfolios/${pid}/ai/analyze`,
      { method: "POST", body: JSON.stringify({ model_id: modelId ?? null }) },
    ),
  aiRecommendations: (pid: string) =>
    request<RecommendationView[]>(`/portfolios/${pid}/ai/recommendations`),
  aiApprove: (pid: string, recId: string) =>
    request<{ recommendation: RecommendationView; outcome: { status: string; reason?: string } | null }>(
      `/portfolios/${pid}/ai/recommendations/${recId}/approve`,
      { method: "POST" },
    ),
  aiReject: (pid: string, recId: string) =>
    request<RecommendationView>(`/portfolios/${pid}/ai/recommendations/${recId}/reject`, {
      method: "POST",
    }),
  listStrategies: () => request<StrategyView[]>("/strategies"),
  createStrategy: (body: object) =>
    request<StrategyView>("/strategies", { method: "POST", body: JSON.stringify(body) }),
  deleteStrategy: (id: string) => request<void>(`/strategies/${id}`, { method: "DELETE" }),
  startBacktest: (id: string, range: string) =>
    request<{ run_id: string }>(`/strategies/${id}/backtest`, {
      method: "POST",
      body: JSON.stringify({ range }),
    }),
  listBacktests: (id: string) => request<BacktestRunView[]>(`/strategies/${id}/backtests`),
  getBacktest: (runId: string) => request<BacktestRunView>(`/strategies/backtests/${runId}`),
  whatIf: (pid: string, scenario: object, range: string) =>
    request<WhatIfResult>(`/portfolios/${pid}/whatif`, {
      method: "POST",
      body: JSON.stringify({ scenario, range }),
    }),
  modules: () =>
    request<{ modules: ModuleView[]; presets: PresetView[] }>("/modules"),
  setModule: (id: string, enabled: boolean) =>
    request<{ applies: string; dependents_affected: string[] }>(`/modules/${id}`, {
      method: "PUT",
      body: JSON.stringify({ enabled }),
    }),
  gamifyProfile: () => request<GamifyProfile>("/gamify/profile"),
  updateGamifyProfile: (body: object) =>
    request<{ ok: boolean }>("/gamify/profile", { method: "PATCH", body: JSON.stringify(body) }),
  gamifyChallenges: () => request<ChallengeView[]>("/gamify/challenges"),
  gamifyEvent: (kind: string, reason = "", portfolioId?: string) =>
    request<{ awarded: boolean }>("/gamify/events", {
      method: "POST",
      body: JSON.stringify({ kind, reason, portfolio_id: portfolioId ?? null }),
    }),
  gamifyEvaluate: () =>
    request<{ achievements_granted: number; challenges_completed: number }>(
      "/gamify/evaluate",
      { method: "POST" },
    ),
  reportCard: (pid: string) => request<ReportCard>(`/portfolios/${pid}/report-card`),
  coach: (pid: string) =>
    request<{ observations: CoachObservation[] }>(`/portfolios/${pid}/coach`),
  gameView: (pid: string) =>
    request<{ mode: string; game_xp: number; game_level: number; ends_at: string | null }>(
      `/portfolios/${pid}/game`,
    ),
  aiSettings: (pid: string) => request<AiSettings>(`/portfolios/${pid}/ai/settings`),
  aiUpdateSettings: (pid: string, body: object) =>
    request<AiSettings>(`/portfolios/${pid}/ai/settings`, {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  // ---- M7: community, sharing, leaderboards, discord ----
  listCompetitions: () => request<CompetitionView[]>("/competitions"),
  createCompetition: (body: object) =>
    request<CompetitionView>("/competitions", { method: "POST", body: JSON.stringify(body) }),
  joinCompetition: (id: string, inviteCode: string, displayName: string) =>
    request<{ portfolio_id: string }>(`/competitions/${id}/join`, {
      method: "POST",
      body: JSON.stringify({ invite_code: inviteCode, display_name: displayName }),
    }),
  standings: (id: string) =>
    request<{ competition: CompetitionView; standings: StandingRow[] }>(
      `/competitions/${id}/standings`,
    ),
  listMembers: (pid: string) =>
    request<{ owner: string; members: MemberView[] }>(`/portfolios/${pid}/members`),
  addMember: (pid: string, username: string, role: string) =>
    request<MemberView>(`/portfolios/${pid}/members`, {
      method: "POST",
      body: JSON.stringify({ username, role }),
    }),
  removeMember: (pid: string, username: string) =>
    request<void>(`/portfolios/${pid}/members/${username}`, { method: "DELETE" }),
  listProposals: (pid: string) => request<ProposalView[]>(`/portfolios/${pid}/proposals`),
  createProposal: (pid: string, body: object) =>
    request<ProposalView>(`/portfolios/${pid}/proposals`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  voteProposal: (pid: string, proposalId: string, approve: boolean) =>
    request<ProposalView>(`/portfolios/${pid}/proposals/${proposalId}/vote`, {
      method: "POST",
      body: JSON.stringify({ approve }),
    }),
  listClubs: () => request<ClubSummary[]>("/clubs"),
  createClub: (body: object) =>
    request<ClubView>("/clubs", { method: "POST", body: JSON.stringify(body) }),
  joinClub: (inviteCode: string) =>
    request<{ id: string; name: string }>("/clubs/join", {
      method: "POST",
      body: JSON.stringify({ invite_code: inviteCode }),
    }),
  clubDetail: (id: string) => request<ClubView>(`/clubs/${id}`),
  deleteClub: (id: string) => request<void>(`/clubs/${id}`, { method: "DELETE" }),
  clubMessages: (id: string) => request<ClubMessageView[]>(`/clubs/${id}/messages`),
  postClubMessage: (id: string, body: string) =>
    request<ClubMessageView>(`/clubs/${id}/messages`, {
      method: "POST",
      body: JSON.stringify({ body }),
    }),
  clubRankings: (id: string) => request<ClubRankRow[]>(`/clubs/${id}/rankings`),
  leaveClub: (id: string, username: string) =>
    request<void>(`/clubs/${id}/members/${username}`, { method: "DELETE" }),
  sharePortfolio: (pid: string) =>
    request<{ token: string; url: string }>(`/shares/portfolios/${pid}`, { method: "POST" }),
  shareStrategy: (sid: string) =>
    request<{ token: string; url: string }>(`/shares/strategies/${sid}`, { method: "POST" }),
  listShares: () => request<ShareLinkView[]>("/shares"),
  revokeShare: (token: string) => request<void>(`/shares/${token}`, { method: "DELETE" }),
  sharedView: (token: string) =>
    request<SharedPortfolioView | SharedStrategyView>(`/shared/${token}`),
  importSharedStrategy: (token: string) =>
    request<{ id: string; name: string }>(`/shares/${token}/import`, { method: "POST" }),
  leaderboards: () => request<{ categories: LeaderboardCategory[] }>("/leaderboards"),
  discordConfig: () => request<DiscordConfigView>("/discord/config"),
  setDiscordConfig: (body: object) =>
    request<{ ok: boolean; note: string }>("/discord/config", {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  discordTest: () => request<{ ok: boolean }>("/discord/test", { method: "POST" }),
  discordPreview: (command: string, arg = "") =>
    request<{ command: string; reply: string }>("/discord/commands/preview", {
      method: "POST",
      body: JSON.stringify({ command, arg }),
    }),
  // M8
  mentor: () => request<MentorView>("/mentor"),
  mentorRefresh: () => request<MentorView>("/mentor/refresh", { method: "POST" }),
  mentorAcknowledge: (id: string) =>
    request<{ ok: boolean }>(`/mentor/observations/${id}/acknowledge`, { method: "POST" }),
  mentorNarrative: () =>
    request<{ narrative: string }>("/mentor/narrative", { method: "POST" }),
  scenarios: () =>
    request<{ catalog: ScenarioInfo[]; sessions: { id: string; scenario_id: string; completed: boolean; created_at: string }[] }>("/scenarios"),
  startScenario: (scenarioId: string, displayName = "") =>
    request<ScenarioSessionView>("/scenarios/sessions", {
      method: "POST",
      body: JSON.stringify({ scenario_id: scenarioId, display_name: displayName }),
    }),
  scenarioSession: (id: string) =>
    request<ScenarioSessionView>(`/scenarios/sessions/${id}`),
  scenarioTrade: (id: string, body: object) =>
    request<{ order_id: string; status: string; filled_price: string | null }>(
      `/scenarios/sessions/${id}/trade`,
      { method: "POST", body: JSON.stringify(body) },
    ),
  scenarioAdvance: (id: string, days: number) =>
    request<ScenarioSessionView>(`/scenarios/sessions/${id}/advance`, {
      method: "POST",
      body: JSON.stringify({ days }),
    }),
  scenarioComparison: (id: string) =>
    request<ScenarioComparison>(`/scenarios/sessions/${id}/comparison`),
  abandonScenario: (id: string) =>
    request<void>(`/scenarios/sessions/${id}`, { method: "DELETE" }),
  career: () => request<CareerView>("/career"),
  careerEvaluate: () => request<CareerView>("/career/evaluate", { method: "POST" }),
  mandates: () => request<{ id: string; name: string; summary: string }[]>("/career/mandates"),
  getMandate: (pid: string) => request<MandateCompliance>(`/portfolios/${pid}/mandate`),
  setMandate: (pid: string, mandate: string) =>
    request<MandateCompliance>(`/portfolios/${pid}/mandate`, {
      method: "PUT",
      body: JSON.stringify({ mandate }),
    }),
  classrooms: () => request<ClassroomView[]>("/classrooms"),
  createClassroom: (name: string) =>
    request<ClassroomView>("/classrooms", { method: "POST", body: JSON.stringify({ name }) }),
  joinClassroom: (inviteCode: string) =>
    request<{ id: string; name: string }>("/classrooms/join", {
      method: "POST",
      body: JSON.stringify({ invite_code: inviteCode }),
    }),
  classroomDetail: (id: string) => request<ClassroomView>(`/classrooms/${id}`),
  deleteClassroom: (id: string) => request<void>(`/classrooms/${id}`, { method: "DELETE" }),
  createAssignment: (classroomId: string, body: object) =>
    request<AssignmentView>(`/classrooms/${classroomId}/assignments`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  assignments: (classroomId: string) =>
    request<AssignmentView[]>(`/classrooms/${classroomId}/assignments`),
  startAssignment: (assignmentId: string) =>
    request<{ portfolio_id: string; scenario_session_id: string | null }>(
      `/assignments/${assignmentId}/start`,
      { method: "POST" },
    ),
  classroomProgress: (id: string) =>
    request<ClassroomProgress>(`/classrooms/${id}/progress`),
  // M9
  aiProfiles: () => request<AiProfileInfo[]>("/ai-players/profiles"),
  addAiPlayer: (competitionId: string, body: object) =>
    request<AiPlayerView>(`/competitions/${competitionId}/ai-players`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  listAiPlayers: (competitionId: string) =>
    request<AiPlayerView[]>(`/competitions/${competitionId}/ai-players`),
  aiDecisions: (playerId: string) =>
    request<{ player: string; decisions: AiDecisionView[] }>(
      `/ai-players/${playerId}/decisions`,
    ),
  aiForceCycle: (playerId: string) =>
    request<{ decisions: number }>(`/ai-players/${playerId}/cycle`, { method: "POST" }),
  tournaments: () => request<TournamentInfo[]>("/tournaments"),
  startTournament: (template: string) =>
    request<{ competition_id: string; portfolio_id: string }>("/tournaments", {
      method: "POST",
      body: JSON.stringify({ template }),
    }),
  competitionAnalysis: (competitionId: string) =>
    request<CompetitionAnalysis>(`/competitions/${competitionId}/analysis`),
  // M10
  learnConcepts: (q = "", category = "") =>
    request<{ categories: { id: string; name: string }[]; concepts: ConceptSummary[] }>(
      `/learn/concepts?q=${encodeURIComponent(q)}&category=${category}`,
    ),
  learnConcept: (id: string) => request<ConceptDetail>(`/learn/concepts/${id}`),
  submitQuiz: (id: string, answers: number[]) =>
    request<QuizResult>(`/learn/concepts/${id}/quiz`, {
      method: "POST",
      body: JSON.stringify({ answers }),
    }),
  learnPaths: () => request<PathView[]>("/learn/paths"),
  learnProgress: () => request<LearnProgress>("/learn/progress"),
  learnSuggestions: () => request<LearnSuggestion[]>("/learn/suggestions"),
  askConcept: (id: string, mode: string, extra: object = {}) =>
    request<{ answer: string }>(`/learn/concepts/${id}/ask`, {
      method: "POST",
      body: JSON.stringify({ mode, ...extra }),
    }),
  simulate: (kind: string, params: object) =>
    request<Record<string, unknown>>(`/learn/simulate/${kind}`, {
      method: "POST",
      body: JSON.stringify({ params }),
    }),
  // M11
  companyProfile: (symbol: string) =>
    request<Record<string, string | number | null>>(`/marketdata/profile/${symbol}`),
  companyNews: (symbol: string) =>
    request<{ title: string; publisher: string; link: string; published_at: number | null }[]>(
      `/marketdata/news/${symbol}`,
    ),
  companySummary: (symbol: string) =>
    request<{ summary: string }>(`/marketdata/summary/${symbol}`, { method: "POST" }),
  listGames: () =>
    request<{ id: string | null; name: string; portfolios: number }[]>("/games"),
  createGame: (name: string) =>
    request<{ id: string; name: string }>("/games", {
      method: "POST",
      body: JSON.stringify({ name }),
    }),
  deleteGame: (id: string) => request<void>(`/games/${id}`, { method: "DELETE" }),
  networth: (range: string, inflationPct: number, gameId = "") =>
    request<{ points: { date: string; value: number; real_value?: number }[];
              portfolios: number; note: string }>(
      `/networth?range=${range}&inflation_pct=${inflationPct}&game_id=${gameId}`,
    ),
  futureSessions: () =>
    request<{ disclaimer: string; sessions: { id: string; symbols: string;
      step: number; virtual_date: string }[] }>("/future"),
  futureStart: (symbols: string[], startingCash: string) =>
    request<FutureView>("/future/sessions", {
      method: "POST",
      body: JSON.stringify({ symbols, starting_cash: startingCash }),
    }),
  futureGet: (id: string) => request<FutureView>(`/future/sessions/${id}`),
  futureTrade: (id: string, body: object) =>
    request<{ status: string; filled_price: string | null }>(
      `/future/sessions/${id}/trade`,
      { method: "POST", body: JSON.stringify(body) },
    ),
  futureAdvance: (id: string, days: number) =>
    request<FutureView>(`/future/sessions/${id}/advance`, {
      method: "POST",
      body: JSON.stringify({ days }),
    }),
  futureAbandon: (id: string) =>
    request<void>(`/future/sessions/${id}`, { method: "DELETE" }),
  listUsers: () => request<UserView[]>("/admin/users"),
  createUser: (body: object) =>
    request<UserView>("/admin/users", { method: "POST", body: JSON.stringify(body) }),
  deleteUser: (username: string) =>
    request<void>(`/admin/users/${username}`, { method: "DELETE" }),
};

export function fmtMoney(v: string | null | undefined, currency = "USD"): string {
  if (v === null || v === undefined || v === "") return "—";
  const n = Number(v);
  return n.toLocaleString(undefined, {
    style: "currency",
    currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

export function pnlClass(v: string | null | undefined): string {
  if (v === null || v === undefined) return "";
  const n = Number(v);
  return n > 0 ? "gain" : n < 0 ? "loss" : "";
}
