"""The investment dictionary (roadmap 10.1-10.2, 10.6, 10.11-10.12).

Every concept carries three explanation levels (beginner / intermediate /
advanced), a category, related terms, and optionally a quiz. Content is
educational material about investing concepts — factual, level-appropriate,
and never advice. Learning paths (10.12) are ordered concept sequences.
"""

from dataclasses import dataclass, field

CATEGORIES = {
    "basics": "Investing Basics",
    "portfolio": "Portfolio Management",
    "metrics": "Financial Metrics",
    "technical": "Technical Analysis",
    "economics": "Economics",
    "strategies": "Strategies",
}


@dataclass(frozen=True)
class Quiz:
    question: str
    options: tuple[str, ...]
    answer: int  # index into options
    why: str


@dataclass(frozen=True)
class Concept:
    id: str
    term: str
    category: str
    beginner: str
    intermediate: str
    advanced: str
    related: tuple[str, ...] = ()
    quiz: tuple[Quiz, ...] = field(default_factory=tuple)


CONCEPTS: dict[str, Concept] = {c.id: c for c in [
    # ------------------------------------------------------------- basics
    Concept(
        id="stock", term="Stock", category="basics",
        beginner="A stock is a tiny piece of ownership in a company. If the "
                 "company does well, your piece can become more valuable.",
        intermediate="A share of common stock is a claim on a company's "
                     "residual earnings and assets, with voting rights. "
                     "Returns come from price appreciation and dividends.",
        advanced="Common equity sits last in the capital structure — behind "
                 "debt and preferred — which is why it carries both the "
                 "highest risk and the highest expected long-run return. Its "
                 "value is the market's discounted estimate of all future "
                 "free cash flows attributable to shareholders.",
        related=("dividend", "market_cap", "etf"),
        quiz=(
            Quiz("Owning a stock means you…",
                 ("Lent money to a company", "Own a piece of a company",
                  "Are guaranteed a profit", "Work for the company"),
                 1, "A share is fractional ownership; lenders own bonds, and "
                    "nothing about equity is guaranteed."),
        ),
    ),
    Concept(
        id="etf", term="ETF (Exchange-Traded Fund)", category="basics",
        beginner="An ETF is a basket of many investments you can buy as one "
                 "thing. One purchase can spread your money across hundreds "
                 "of companies.",
        intermediate="ETFs hold a portfolio of securities (often tracking an "
                     "index like the S&P 500) and trade on exchanges like a "
                     "stock. They offer instant diversification with low fees.",
        advanced="The creation/redemption mechanism lets authorized "
                 "participants arbitrage the ETF price against its net asset "
                 "value, keeping tracking error small and making ETFs more "
                 "tax-efficient than mutual funds in most jurisdictions.",
        related=("diversification", "index_investing", "stock"),
        quiz=(
            Quiz("The main benefit of a broad-market ETF is…",
                 ("Guaranteed returns", "Instant diversification at low cost",
                  "It always beats stock-picking", "No risk"),
                 1, "One share spreads your money across the whole index — "
                    "cheap diversification, not a guarantee."),
        ),
    ),
    Concept(
        id="bond", term="Bond", category="basics",
        beginner="A bond is a loan you make to a company or government. They "
                 "pay you interest and return your money at the end.",
        intermediate="Bonds pay fixed coupons and repay principal at "
                     "maturity. Prices move inversely to interest rates; "
                     "credit quality determines default risk.",
        advanced="Bond risk decomposes into duration (rate sensitivity ≈ "
                 "percentage price change per 1% yield move), convexity, and "
                 "credit spread. Long-duration bonds hedge equity drawdowns "
                 "in disinflationary recessions but suffer in inflation "
                 "shocks — 2022 was the canonical example.",
        related=("interest_rates", "inflation", "asset_allocation"),
    ),
    Concept(
        id="dividend", term="Dividend", category="basics",
        beginner="A dividend is cash a company pays its owners, usually every "
                 "three months — like rent from owning a slice of the business.",
        intermediate="Dividends are distributions of earnings. Dividend yield "
                     "= annual dividend / share price. Reinvesting dividends "
                     "historically contributed a large share of total equity "
                     "returns.",
        advanced="Dividend policy is a capital-allocation signal: stable "
                 "growing dividends imply management confidence in cash "
                 "flows, while ultra-high yields often price in an expected "
                 "cut. Total-return investors treat buybacks and dividends as "
                 "near-equivalent shareholder yield, taxes aside.",
        related=("dividend_yield", "compound_growth", "dividend_investing"),
        quiz=(
            Quiz("A stock at $100 paying $3/year in dividends yields…",
                 ("0.3%", "3%", "30%", "$3 is not a yield"),
                 1, "Yield = 3 / 100 = 3%."),
        ),
    ),
    Concept(
        id="market_cap", term="Market Cap", category="basics",
        beginner="Market cap is what the whole company is worth on the stock "
                 "market: the share price times the number of shares.",
        intermediate="Market capitalization = price × shares outstanding. "
                     "Companies are grouped into large-cap (>$10B), mid-cap, "
                     "and small-cap, which behave differently as groups.",
        advanced="Cap-weighting makes indices momentum-tilted: winners grow "
                 "their own index weight. Free-float adjustment excludes "
                 "insider holdings. Size is one of the classic Fama-French "
                 "return factors, though the small-cap premium has weakened "
                 "since its discovery.",
        related=("stock", "index_investing", "pe_ratio"),
    ),
    Concept(
        id="compound_growth", term="Compound Growth", category="basics",
        beginner="Compounding means your gains start earning their own gains. "
                 "Money left invested grows faster and faster over time.",
        intermediate="Value grows as (1+r)^n — returns are applied to an "
                     "ever-larger base. At 7%/year money doubles roughly "
                     "every 10 years (the rule of 72: 72 ÷ rate ≈ years to "
                     "double).",
        advanced="Compounding is geometric, so volatility drags realized "
                 "returns below the arithmetic mean (variance drain ≈ σ²/2). "
                 "This is why a -50% loss needs +100% to recover, and why "
                 "long horizons and drawdown control dominate return-chasing.",
        related=("dca", "volatility", "risk"),
        quiz=(
            Quiz("At 7% annual growth, money roughly doubles every…",
                 ("2 years", "10 years", "25 years", "50 years"),
                 1, "Rule of 72: 72 ÷ 7 ≈ 10 years."),
            Quiz("After a 50% loss, getting back to even requires…",
                 ("+50%", "+75%", "+100%", "+25%"),
                 2, "Half of your money must double just to break even — "
                    "losses hurt more than equal-sized gains help."),
        ),
    ),
    # ---------------------------------------------------------- portfolio
    Concept(
        id="diversification", term="Diversification", category="portfolio",
        beginner="Don't put all your eggs in one basket. Owning many "
                 "different investments means one bad one can't ruin you.",
        intermediate="Combining assets that don't move together lowers "
                     "portfolio volatility without proportionally lowering "
                     "expected return — the only 'free lunch' in investing. "
                     "It works across companies, sectors, countries, and "
                     "asset classes.",
        advanced="Portfolio variance = Σwᵢwⱼσᵢσⱼρᵢⱼ; with correlation below "
                 "1, total risk falls below the weighted average of parts. "
                 "Idiosyncratic risk diversifies away with ~20-30 uncorrelated "
                 "names; systematic (market) risk does not. Correlations "
                 "converge toward 1 in crises — exactly when you need them low.",
        related=("concentration_risk", "asset_allocation", "correlation",
                 "geographic_diversification"),
        quiz=(
            Quiz("Diversification mainly protects you against…",
                 ("Market-wide crashes", "One company blowing up",
                  "Inflation", "Taxes"),
                 1, "Spreading positions removes single-company "
                    "(idiosyncratic) risk; market-wide risk remains."),
        ),
    ),
    Concept(
        id="concentration_risk", term="Concentration Risk", category="portfolio",
        beginner="If most of your money is in one stock or one industry, one "
                 "piece of bad news can hit almost everything you own at once.",
        intermediate="A position or sector dominating the portfolio ties your "
                     "outcome to a single story. Even great companies "
                     "regularly draw down 50%+; concentration turns that "
                     "into a portfolio event.",
        advanced="Concentration is uncompensated risk: the market does not "
                 "pay you extra expected return for holding diversifiable "
                 "exposure. Kelly-style sizing caps any single bet by edge "
                 "and variance; institutional mandates typically cap single "
                 "names at 5-10% for this reason.",
        related=("diversification", "risk", "asset_allocation"),
    ),
    Concept(
        id="geographic_diversification", term="Geographic Diversification",
        category="portfolio",
        beginner="Owning only your home country's stocks ties your savings to "
                 "one economy. Spreading across countries softens local "
                 "problems.",
        intermediate="Home bias concentrates currency, political, and "
                     "economic-cycle risk. International allocations have "
                     "meaningfully different sector mixes (e.g. US = tech-"
                     "heavy, Europe = financials/industrials).",
        advanced="Country returns diverge for decades (Japan 1990-2020 vs "
                 "the US). Currency exposure is a separate decision — hedged "
                 "vs unhedged international bonds behave very differently. "
                 "Global-cap weighting is the neutral starting point; any "
                 "home overweight is an active bet.",
        related=("diversification", "correlation"),
    ),
    Concept(
        id="asset_allocation", term="Asset Allocation", category="portfolio",
        beginner="How you split money between stocks, bonds, and cash. This "
                 "split matters more than which exact stocks you pick.",
        intermediate="Allocation sets the portfolio's risk level: stocks for "
                     "growth, bonds for stability, cash for optionality. "
                     "Landmark studies attribute the large majority of "
                     "return variability between portfolios to allocation, "
                     "not security selection.",
        advanced="Allocation is the primary lever on the efficient frontier. "
                 "Risk-based approaches (risk parity) size by volatility "
                 "contribution rather than capital. Glide paths shift from "
                 "equities toward bonds as the investing horizon shortens — "
                 "sequence-of-returns risk dominates near withdrawal time.",
        related=("diversification", "rebalancing", "risk"),
    ),
    Concept(
        id="rebalancing", term="Rebalancing", category="portfolio",
        beginner="Over time winners grow and unbalance your plan. Rebalancing "
                 "sells a little of what grew and buys what shrank, back to "
                 "your target mix.",
        intermediate="Rebalancing enforces buy-low/sell-high discipline and "
                     "keeps risk at its intended level. Common triggers: "
                     "calendar (quarterly/annual) or threshold (±5% drift).",
        advanced="Rebalancing harvests a diversification premium when assets "
                 "mean-revert, but drags in strong trends (momentum). "
                 "Threshold rebalancing dominates calendar in most studies; "
                 "in taxable accounts, rebalance with new contributions to "
                 "avoid realizing gains.",
        related=("asset_allocation", "diversification"),
    ),
    Concept(
        id="risk", term="Risk", category="portfolio",
        beginner="Risk is the chance your investment loses value — and how "
                 "bad that loss could be. Higher possible rewards come with "
                 "higher risk.",
        intermediate="Practitioners measure risk as volatility (how much "
                     "returns swing) and max drawdown (worst peak-to-trough "
                     "loss). Your real risk tolerance is how much drawdown "
                     "you can sit through without selling.",
        advanced="Volatility is a convenient but incomplete proxy: returns "
                 "are fat-tailed and left-skewed, so VaR/CVaR and drawdown "
                 "statistics capture tail risk better. Permanent capital "
                 "loss and forced selling at the bottom — not variance per "
                 "se — are the risks that actually end compounding.",
        related=("volatility", "max_drawdown", "sharpe_ratio"),
    ),
    Concept(
        id="volatility", term="Volatility", category="portfolio",
        beginner="Volatility is how bumpy the ride is. A volatile investment "
                 "jumps around a lot day to day, even if it grows long-term.",
        intermediate="Measured as the annualized standard deviation of "
                     "returns. Broad stock indices historically run ~15-20%; "
                     "single stocks are often 30-60%+.",
        advanced="Volatility clusters (GARCH effects) and is itself tradable "
                 "(VIX). Realized vol underestimates crash risk because of "
                 "fat tails. Position sizing by inverse volatility equalizes "
                 "risk contributions — the core of risk-parity construction.",
        related=("risk", "beta", "sharpe_ratio"),
    ),
    Concept(
        id="max_drawdown", term="Max Drawdown", category="portfolio",
        beginner="The worst drop from a high point to a low point. It answers: "
                 "'how bad did it get for someone who bought at the top?'",
        intermediate="Max drawdown measures the deepest peak-to-trough "
                     "decline. It captures the pain of a strategy better "
                     "than volatility — and recovery time matters as much "
                     "as depth.",
        advanced="Drawdown scales nonlinearly with recovery: -20% needs "
                 "+25%, -50% needs +100%. Calmar ratio (CAGR / max DD) "
                 "rewards drawdown control. For withdrawal-phase portfolios, "
                 "drawdown plus withdrawals creates sequence risk that can "
                 "permanently impair capital.",
        related=("risk", "volatility", "compound_growth"),
    ),
    Concept(
        id="correlation", term="Correlation", category="portfolio",
        beginner="Correlation is whether two investments move together. "
                 "Mixing things that don't move together makes the total "
                 "smoother.",
        intermediate="Ranges from +1 (move identically) to -1 (move "
                     "opposite). Diversification's power comes entirely from "
                     "combining assets with correlation below +1.",
        advanced="Correlations are unstable and regime-dependent: equity "
                 "pairwise correlations spike toward 1 in liquidity crises. "
                 "Stock-bond correlation flipped positive in the 2022 "
                 "inflation shock after two negative decades — allocation "
                 "models built on the old regime failed simultaneously.",
        related=("diversification", "asset_allocation"),
    ),
    # ------------------------------------------------------------ metrics
    Concept(
        id="pe_ratio", term="P/E Ratio", category="metrics",
        beginner="Price divided by yearly profit per share. It tells you how "
                 "many years of today's profits you're paying for.",
        intermediate="P/E = price / earnings per share. High P/E means the "
                     "market expects strong growth (or the stock is "
                     "expensive); low P/E means low expectations (or a "
                     "bargain). Compare within industries, not across them.",
        advanced="The inverse (earnings yield) compares directly to bond "
                 "yields. Forward vs trailing P/E differ by expected growth; "
                 "cyclically-adjusted CAPE smooths the earnings cycle. P/E "
                 "expansion/contraction, not earnings, drives most short-run "
                 "index returns.",
        related=("eps", "market_cap", "value_investing"),
        quiz=(
            Quiz("A stock at $50 with $2.50 EPS has a P/E of…",
                 ("5", "20", "50", "125"),
                 1, "50 ÷ 2.50 = 20 — you pay 20 years of current earnings."),
        ),
    ),
    Concept(
        id="eps", term="EPS (Earnings Per Share)", category="metrics",
        beginner="The company's profit divided by its number of shares — the "
                 "profit that belongs to each share you own.",
        intermediate="EPS = net income / shares outstanding. Growing EPS "
                     "drives long-run stock returns; diluted EPS accounts "
                     "for options and convertibles.",
        advanced="EPS is manageable: buybacks raise it without operating "
                 "improvement, and non-GAAP adjustments routinely flatter "
                 "it. Cross-check with free cash flow per share and revenue "
                 "growth to separate financial engineering from real "
                 "earnings power.",
        related=("pe_ratio", "revenue", "cash_flow"),
    ),
    Concept(
        id="revenue", term="Revenue", category="metrics",
        beginner="All the money a company brings in from selling its products "
                 "— the 'top line', before any costs are paid.",
        intermediate="Revenue growth shows demand; margins show how much of "
                     "it survives to profit. A company can grow revenue and "
                     "still lose money.",
        advanced="Revenue quality matters: recurring subscription revenue "
                 "deserves a higher multiple than one-off hardware sales. "
                 "Revenue recognition rules (ASC 606) create timing "
                 "differences between bookings, billings, and reported "
                 "revenue that growth investors track closely.",
        related=("eps", "cash_flow"),
    ),
    Concept(
        id="cash_flow", term="Cash Flow", category="metrics",
        beginner="The actual cash moving in and out of a business. Profits on "
                 "paper don't pay bills — cash does.",
        intermediate="Operating cash flow strips out accounting adjustments "
                     "from net income. Free cash flow (FCF) = operating cash "
                     "flow − capital spending: money genuinely available to "
                     "shareholders.",
        advanced="FCF is the basis of discounted-cash-flow valuation. "
                 "Persistent gaps between net income and FCF (high accruals) "
                 "predict earnings disappointments. Capitalized costs, "
                 "working-capital swings, and stock-based compensation are "
                 "the usual reconciling culprits.",
        related=("eps", "revenue", "value_investing"),
    ),
    Concept(
        id="dividend_yield", term="Dividend Yield", category="metrics",
        beginner="The yearly dividend as a percentage of the price — like an "
                 "interest rate for owning the stock.",
        intermediate="Yield = annual dividends / price. A 'high' yield can "
                     "mean generous payout or a falling price ahead of a "
                     "dividend cut — check the payout ratio.",
        advanced="Payout ratio (dividends/earnings) and FCF coverage "
                 "determine sustainability. Yield traps cluster where "
                 "payout > 100% of FCF. Dividend growth rate compounds: a "
                 "2% yield growing 10%/yr out-earns a static 4% yield "
                 "within a decade on cost basis.",
        related=("dividend", "dividend_investing", "pe_ratio"),
    ),
    Concept(
        id="beta", term="Beta", category="metrics",
        beginner="Beta measures how strongly a stock moves when the whole "
                 "market moves. Beta 1 = moves like the market; 2 = twice as "
                 "hard; 0.5 = half.",
        intermediate="Beta is the regression slope of a stock's returns on "
                     "market returns. High-beta stocks amplify both rallies "
                     "and crashes; low-beta stocks dampen them.",
        advanced="Beta = cov(rᵢ, rₘ)/var(rₘ) — the CAPM's priced risk. "
                 "Empirically the security market line is too flat "
                 "('betting against beta'): low-beta stocks earn more than "
                 "CAPM predicts, likely due to leverage constraints. Beta is "
                 "also unstable through time; use it as a rough exposure "
                 "gauge, not a constant.",
        related=("volatility", "risk", "sharpe_ratio"),
    ),
    Concept(
        id="sharpe_ratio", term="Sharpe Ratio", category="metrics",
        beginner="A score for return earned per unit of risk taken. Higher is "
                 "better: more reward for the same amount of bumpiness.",
        intermediate="Sharpe = (return − risk-free rate) / volatility. It "
                     "lets you compare strategies with different risk "
                     "levels; above ~1 over long periods is strong.",
        advanced="Sharpe assumes normal returns, so it flatters strategies "
                 "that sell tail risk (steady small gains, rare huge "
                 "losses). Sortino (downside deviation) and Calmar "
                 "(drawdown) address the asymmetry. Annualize with √252 for "
                 "daily data and mind autocorrelation, which inflates it.",
        related=("volatility", "risk", "max_drawdown"),
    ),
    # ----------------------------------------------------------- technical
    Concept(
        id="moving_average", term="Moving Average", category="technical",
        beginner="The average price over the last N days, drawn as a smooth "
                 "line. It shows the trend by ignoring daily noise.",
        intermediate="Simple (SMA) and exponential (EMA) averages smooth "
                     "price series. Common signals: price crossing the "
                     "200-day, or the 50-day crossing the 200-day ('golden/"
                     "death cross').",
        advanced="MA rules are slow-momentum filters: they lag by "
                 "construction, trading whipsaws in ranges for participation "
                 "in trends. Trend-following on MAs historically cut equity "
                 "drawdowns at the cost of lag-induced underperformance in "
                 "V-shaped recoveries (2020).",
        related=("momentum", "rsi", "macd"),
    ),
    Concept(
        id="rsi", term="RSI (Relative Strength Index)", category="technical",
        beginner="A 0-100 gauge of whether a stock has recently gone up or "
                 "down too fast. Above 70 = maybe overheated; below 30 = "
                 "maybe oversold.",
        intermediate="RSI compares average recent gains to losses over (by "
                     "default) 14 periods. Extremes flag potential "
                     "exhaustion, but strong trends can stay 'overbought' "
                     "for months.",
        advanced="RSI = 100 − 100/(1+RS), RS = smoothed gain/loss ratio. "
                 "Mean-reversion signals from RSI work best in range-bound "
                 "regimes and fail in trends; divergences (price high, RSI "
                 "lower high) are the higher-quality signal. Parameterize "
                 "and test — defaults are folklore, not laws.",
        related=("momentum", "moving_average", "macd"),
    ),
    Concept(
        id="macd", term="MACD", category="technical",
        beginner="A trend gauge built from two moving averages. When its "
                 "lines cross, the trend may be changing direction.",
        intermediate="MACD = 12-period EMA − 26-period EMA, with a 9-period "
                     "signal line. Crossovers and the histogram's slope "
                     "track momentum shifts.",
        advanced="MACD is a band-pass filter on price: it isolates a "
                 "specific frequency of trend. All parameters imply a "
                 "holding-period bet; crossovers lag turns and mean-revert "
                 "in choppy tape. Combine with volatility filters to cut "
                 "false signals.",
        related=("moving_average", "momentum", "rsi"),
    ),
    Concept(
        id="momentum", term="Momentum", category="technical",
        beginner="The tendency of things that have been going up to keep "
                 "going up for a while (and falling things to keep falling).",
        intermediate="Cross-sectional momentum buys the recent best "
                     "performers (typically 3-12 month lookback) and holds "
                     "1-3 months. One of the most persistent patterns in "
                     "market history.",
        advanced="Momentum earns a premium across asset classes and "
                 "centuries of data, but with brutal left tails: momentum "
                 "crashes occur at bear-market turns (2009), when the "
                 "short-loser leg rips. Skip the most recent month to avoid "
                 "short-term reversal; volatility-scale to tame crashes.",
        related=("rsi", "moving_average", "growth_investing"),
    ),
    # ---------------------------------------------------------- economics
    Concept(
        id="inflation", term="Inflation", category="economics",
        beginner="Prices rising over time, which quietly shrinks what your "
                 "money can buy. Investing aims to grow faster than inflation.",
        intermediate="Measured by indices like CPI. Even 3% inflation halves "
                     "purchasing power in ~24 years. Real return = nominal "
                     "return − inflation; cash reliably loses to inflation "
                     "long-term.",
        advanced="Unexpected inflation is the asset-price killer: it "
                 "re-rates discount rates, crushing long-duration assets "
                 "(growth stocks, long bonds) simultaneously — the 2022 "
                 "regime. Real assets, TIPS, value stocks, and commodities "
                 "historically hedge better than nominal bonds.",
        related=("interest_rates", "gdp", "bond"),
        quiz=(
            Quiz("At 3% inflation, cash under the mattress in ~24 years buys…",
                 ("The same amount", "About half as much",
                  "About 10% less", "Nothing"),
                 1, "Purchasing power halves at 3% in roughly 72/3 = 24 years "
                    "— the rule of 72 works for erosion too."),
        ),
    ),
    Concept(
        id="interest_rates", term="Interest Rates", category="economics",
        beginner="The price of borrowing money, set largely by central banks. "
                 "When rates rise, loans cost more and investments compete "
                 "with safe savings.",
        intermediate="Central banks raise rates to cool inflation and cut "
                     "them to stimulate. Higher rates pressure stock "
                     "valuations (especially growth) and drop bond prices.",
        advanced="The policy rate anchors the discount curve every asset "
                 "prices from. Equity duration explains growth-stock rate "
                 "sensitivity: cash flows far in the future are discounted "
                 "hardest. Yield-curve inversions have preceded most "
                 "post-war US recessions — a market-implied forecast, not "
                 "a mechanical law.",
        related=("inflation", "bond", "gdp"),
    ),
    Concept(
        id="gdp", term="GDP", category="economics",
        beginner="The total value of everything a country produces in a year "
                 "— the broadest scoreboard of an economy.",
        intermediate="GDP growth drives corporate earnings in aggregate. "
                     "Two consecutive shrinking quarters is a common "
                     "(informal) recession definition.",
        advanced="Equity returns correlate surprisingly weakly with GDP "
                 "growth across countries (growth gets priced in and "
                 "diluted by share issuance). Markets lead the cycle: "
                 "equities typically bottom mid-recession, long before GDP "
                 "turns.",
        related=("inflation", "interest_rates"),
    ),
    Concept(
        id="market_cycle", term="Market Cycles", category="economics",
        beginner="Markets move in repeating moods: growth, euphoria, panic, "
                 "recovery. No mood lasts forever, in either direction.",
        intermediate="Bull markets historically run for years; bear markets "
                     "(-20%+) are shorter but violent. Timing them "
                     "consistently has defeated nearly everyone — missing "
                     "the 10 best days per decade destroys returns.",
        advanced="Cycles emerge from credit expansion/contraction and "
                 "valuation mean-reversion. Regime models (recession vs "
                 "expansion, high/low vol) improve risk management even "
                 "when point-timing fails. The behavioral cycle — greed to "
                 "capitulation — is the tradable part, via rebalancing "
                 "discipline rather than prediction.",
        related=("inflation", "interest_rates", "momentum"),
    ),
    # ---------------------------------------------------------- strategies
    Concept(
        id="dca", term="Dollar Cost Averaging", category="strategies",
        beginner="Investing the same amount on a schedule (say monthly) no "
                 "matter what the market does. You automatically buy more "
                 "shares when prices are low.",
        intermediate="DCA removes timing decisions and emotion. "
                     "Mathematically, lump-sum investing wins ~2/3 of the "
                     "time (markets rise on average), but DCA's behavioral "
                     "value — you actually stay invested — often dominates.",
        advanced="DCA is a glide path from cash into risk: it trades "
                 "expected return for lower variance of outcomes over the "
                 "entry window and eliminates point-in-time regret. For "
                 "recurring income it's simply optimal; the DCA-vs-lump-sum "
                 "debate only applies to windfalls.",
        related=("compound_growth", "index_investing", "market_cycle"),
        quiz=(
            Quiz("Dollar cost averaging means…",
                 ("Buying only when prices drop", "Investing a fixed amount "
                  "on a schedule", "Averaging analyst targets",
                  "Selling in equal parts"),
                 1, "Fixed amount, fixed schedule — more shares when cheap, "
                    "fewer when expensive, zero timing decisions."),
        ),
    ),
    Concept(
        id="index_investing", term="Index Investing", category="strategies",
        beginner="Instead of picking winners, buy a tiny piece of every "
                 "company in the market through one fund and let the economy "
                 "do the work.",
        intermediate="Index funds hold the market at minimal cost. After "
                     "fees, the majority of professional managers "
                     "underperform their index over 10+ years — costs and "
                     "arithmetic guarantee the average manager can't win.",
        advanced="Sharpe's arithmetic of active management: the "
                 "cap-weighted market return is the average of all "
                 "participants before costs, so after costs the average "
                 "active dollar must lag. Index concentration (top-10 "
                 "weight) periodically raises single-name risk inside "
                 "'passive' portfolios — worth monitoring.",
        related=("etf", "dca", "diversification"),
    ),
    Concept(
        id="value_investing", term="Value Investing", category="strategies",
        beginner="Shopping for companies that look cheap compared to what "
                 "they earn and own — buying dollars for eighty cents and "
                 "waiting.",
        intermediate="Value screens on low P/E, price/book, or high FCF "
                     "yield versus peers. The risk is the 'value trap': "
                     "cheap because the business is dying.",
        advanced="The value premium (HML) is a canonical Fama-French factor "
                 "with deep historical support and a brutal 2010s drawdown. "
                 "Modern implementations adjust book value for intangibles "
                 "and combine value with quality/profitability screens to "
                 "filter traps.",
        related=("pe_ratio", "cash_flow", "growth_investing"),
    ),
    Concept(
        id="growth_investing", term="Growth Investing", category="strategies",
        beginner="Buying companies growing much faster than average, "
                 "accepting a high price today for a much bigger business "
                 "tomorrow.",
        intermediate="Growth investors prioritize revenue/EPS growth rates "
                     "and market opportunity over current valuation. The "
                     "risk: growth priced in that doesn't arrive gets "
                     "punished twice (earnings and multiple).",
        advanced="Growth is a duration bet — value concentrated in distant "
                 "cash flows — hence acute rate sensitivity (2022). "
                 "Sustained hypergrowth is rarer than markets price: base "
                 "rates for 20%+ revenue growth persisting 5+ years are "
                 "in the single digits.",
        related=("value_investing", "momentum", "interest_rates"),
    ),
    Concept(
        id="dividend_investing", term="Dividend Investing", category="strategies",
        beginner="Building a portfolio of companies that pay you regular "
                 "cash, aiming for income that grows every year.",
        intermediate="Focus on dividend growth and payout safety over raw "
                     "yield. Dividend aristocrats (25+ years of raises) "
                     "showcase durable cash generation.",
        advanced="Dividend strategies are implicit quality/low-vol factor "
                 "tilts. In total-return terms a dividend is not free money "
                 "(price drops by the payout ex-date); the strategy's edge "
                 "is discipline and cash-flow durability, not the payout "
                 "mechanics. Tax treatment can dominate in taxable accounts.",
        related=("dividend", "dividend_yield", "value_investing"),
    ),
]}


@dataclass(frozen=True)
class LearningPath:
    id: str
    name: str
    description: str
    concepts: tuple[str, ...]


PATHS: dict[str, LearningPath] = {p.id: p for p in [
    LearningPath(
        id="beginner_investor", name="Beginner Investor",
        description="What you're buying, how markets treat it, and the two "
                    "ideas (risk and diversification) that protect you.",
        concepts=("stock", "etf", "bond", "dividend", "market_cap",
                  "compound_growth", "risk", "diversification", "dca"),
    ),
    LearningPath(
        id="intermediate_investor", name="Intermediate Investor",
        description="Valuation, reading the numbers, and constructing a "
                    "portfolio on purpose.",
        concepts=("pe_ratio", "eps", "revenue", "cash_flow", "dividend_yield",
                  "asset_allocation", "rebalancing", "correlation",
                  "volatility", "index_investing"),
    ),
    LearningPath(
        id="advanced_investor", name="Advanced Investor",
        description="Factors, quantitative measures, and risk beyond "
                    "volatility.",
        concepts=("beta", "sharpe_ratio", "max_drawdown", "momentum",
                  "value_investing", "growth_investing", "market_cycle",
                  "inflation", "interest_rates", "concentration_risk"),
    ),
]}


def concept_view(c: Concept, include_quiz: bool = False) -> dict:
    out = {
        "id": c.id, "term": c.term, "category": c.category,
        "category_name": CATEGORIES[c.category],
        "beginner": c.beginner, "intermediate": c.intermediate,
        "advanced": c.advanced, "related": list(c.related),
        "has_quiz": bool(c.quiz),
    }
    if include_quiz:
        out["quiz"] = [
            {"question": q.question, "options": list(q.options)}
            for q in c.quiz
        ]
    return out


def search(query: str) -> list[Concept]:
    q = query.lower().strip()
    if not q:
        return list(CONCEPTS.values())
    hits = []
    for c in CONCEPTS.values():
        hay = f"{c.term} {c.id} {c.beginner} {c.intermediate}".lower()
        if q in hay:
            hits.append((0 if q in c.term.lower() else 1, c.term, c))
    hits.sort(key=lambda t: (t[0], t[1]))
    return [c for _, _, c in hits]
