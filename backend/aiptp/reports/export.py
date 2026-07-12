"""Report exports v1: CSV, JSON, and Markdown. PDF/XLSX arrive in M4 per the
roadmap."""

import csv
import io
import json
from datetime import datetime, timezone
from typing import Any

TXN_COLUMNS = [
    "executed_at", "symbol", "kind", "side", "quantity", "price",
    "amount", "realized_pnl", "fx_rate", "quote_currency", "origin",
]


def _txn_rows(transactions) -> list[dict[str, Any]]:
    rows = []
    for t in transactions:
        rows.append(
            {
                "executed_at": t.executed_at.isoformat(),
                "symbol": t.symbol,
                "kind": t.kind.value,
                "side": t.side.value,
                "quantity": str(t.quantity),
                "price": str(t.price),
                "amount": str(t.amount),
                "realized_pnl": str(t.realized_pnl) if t.realized_pnl is not None else "",
                "fx_rate": str(t.fx_rate),
                "quote_currency": t.quote_currency,
                "origin": t.origin.value,
            }
        )
    return rows


def to_csv(portfolio_view: dict[str, Any], transactions) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=TXN_COLUMNS)
    writer.writeheader()
    writer.writerows(_txn_rows(transactions))
    return buf.getvalue()


def to_json(portfolio_view: dict[str, Any], transactions, analytics: dict | None) -> str:
    return json.dumps(
        {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "portfolio": portfolio_view,
            "transactions": _txn_rows(transactions),
            "analytics": analytics,
        },
        indent=2,
        default=str,
    )


def to_markdown(portfolio_view: dict[str, Any], transactions, analytics: dict | None) -> str:
    p = portfolio_view
    lines = [
        f"# Portfolio report — {p['name']}",
        "",
        f"Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} · "
        f"currency {p['currency']} · cost basis {p['cost_basis_method']}",
        "",
        "## Summary",
        "",
        f"| Metric | Value |",
        f"| --- | ---: |",
        f"| Total value | {p['total_value']} |",
        f"| Cash | {p['cash_balance']} |",
        f"| Market value | {p['market_value']} |",
        f"| Unrealized P&L | {p['unrealized_pnl']} |",
        f"| Lifetime return | {p['lifetime_return']} |",
        "",
        "## Holdings",
        "",
        "| Symbol | Shares | Avg cost | Price | Market value | Unrealized |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for h in p["holdings"]:
        lines.append(
            f"| {h['symbol']} | {h['quantity']} | {h['avg_cost'] or '—'} | "
            f"{h['price'] or '—'} | {h['market_value'] or '—'} | {h['unrealized_pnl'] or '—'} |"
        )
    if analytics:
        risk = analytics.get("risk", {})
        records = analytics.get("records", {})
        lines += [
            "",
            "## Analytics",
            "",
            "| Metric | Value |",
            "| --- | ---: |",
            f"| Sharpe | {risk.get('sharpe', '—')} |",
            f"| Sortino | {risk.get('sortino', '—')} |",
            f"| Beta | {risk.get('beta', '—')} |",
            f"| Volatility (ann.) | {risk.get('volatility', '—')}% |",
            f"| Max drawdown | {risk.get('max_drawdown', '—')}% |",
            f"| Win rate | {records.get('win_rate', '—')}% |",
            f"| Avg holding period | {records.get('avg_holding_days', '—')} days |",
            f"| Diversification score | {analytics.get('diversification', {}).get('score', '—')} |",
        ]
    lines += ["", "## Transactions", "",
              "| Executed | Symbol | Kind | Side | Qty | Price | Amount | Realized | Origin |",
              "| --- | --- | --- | --- | ---: | ---: | ---: | ---: | --- |"]
    for r in _txn_rows(transactions):
        lines.append(
            f"| {r['executed_at'][:16]} | {r['symbol']} | {r['kind']} | {r['side']} | "
            f"{r['quantity']} | {r['price']} | {r['amount']} | {r['realized_pnl'] or '—'} | {r['origin']} |"
        )
    lines.append("")
    lines.append("*Paper trading only — simulated funds, real market data.*")
    return "\n".join(lines)
