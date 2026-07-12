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
  listPortfolios: () => request<PortfolioView[]>("/portfolios"),
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
