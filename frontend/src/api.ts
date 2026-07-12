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
  type: "MARKET" | "LIMIT" | "STOP" | "STOP_LIMIT";
  quantity: string | null;
  notional: string | null;
  limit_price: string | null;
  stop_price: string | null;
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
  origin: string;
  executed_at: string;
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

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
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
