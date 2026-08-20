# Grow Trade Assistant — Complete Review Brief for External AI

**Purpose of this document:** Paste this entire file (or link to it) into a higher-capability AI for architecture review, research-quality critique, and prioritized improvement suggestions.

**Repository (public):** https://github.com/DakshMeghawat/grow-trade-assistant

**Local path:** `grow-trade-assistant` — Python 3.9+, read-only Indian equity + mutual fund portfolio analysis for a Groww user.

**Disclaimer baked into product:** Education and research only. Not SEBI-registered advice. No order placement. Never present outputs as guaranteed returns.

---

## 1. What this project is

A **personal portfolio analysis assistant** for long-term Indian investing:

- Pulls **stock holdings** from Groww API or imported Groww CSV/XLSX/Numbers
- Pulls **mutual fund holdings** from manually configured `mutual_funds.json` + MFApi.in NAV
- Fetches **live/historical prices** from Yahoo Finance (NSE `.NS` tickers)
- Computes **deterministic metrics** (P&L, weights, MA, RSI, MACD, ATR, drawdown, benchmark comparison)
- Applies **rule-based recommendations** (keep / monitor / research / rebalance-candidate) with counterpoints
- Writes **daily reports** (`reports/YYYY-MM-DD.md` + `.json`) and serves a **local web dashboard** (`grow-assistant dashboard` → http://127.0.0.1:8765)

**Explicit non-goals (today):** Live trading, broker order execution, runtime LLM API calls, backtest engine (schema only), US markets, licensed fundamentals feed.

---

## 2. Design principles we are following

Inspired by FinRobot / FinGPT / daily_stock_analysis patterns and quant best practices:

| Principle | Implementation status |
|-----------|----------------------|
| Separate ingestion, features, analysis, presentation | **Partial** — stages exist; not fully package-isolated |
| Deterministic libraries for prices, ratios, indicators | **Yes** — `features/indicators.py`, `analysis/performance.py` |
| LLM only for explanation / synthesis | **Partial** — investment memo uses **static** Cursor-maintained briefs, not runtime LLM |
| Store source URLs, timestamps, claim types | **Yes** — `domain/provenance.py`, report `provenance` block |
| Distinguish reported vs calculated vs LLM text | **Yes** — `ClaimType` enum in JSON |
| No look-ahead / survivorship in backtests | **Planned** — `backtest/config.py` schema only |
| Compare strategies to buy-and-hold benchmark | **Partial** — snapshot `benchmark_comparison`, not historical backtest |
| Show uncertainty, counterarguments, data freshness | **Yes** — counterpoints on recommendations, staleness warnings, data_warnings |
| No live trading without paper mode | **Yes** — no order endpoints wired |

---

## 3. Architecture (current)

```
Entry points
├── CLI: grow-assistant (cli.py)
├── Web: FastAPI dashboard (web/app.py :8765)
└── Scheduler: EOD weekdays (scheduler.py)

Orchestration
└── pipeline/runner.py → run_analysis()

Ingestion (pipeline/stages.py)
├── ingest_holdings()  → Groww API | import file | SQLite cache
├── ingest_prices()    → Yahoo + optional Groww LTP overlay
└── ingest_ancillary() → MFApi + Google News RSS

Features (deterministic)
└── features/indicators.py → MA50/200, vol, RSI14, MACD, ATR14, drawdown, 1Y/3Y return

Analysis
├── analysis/metrics.py           → position + portfolio metrics
├── analysis/recommendations.py   → rule engine + cooldown
├── analysis/deep_analysis.py       → combined stocks+MF strategy verdict
├── analysis/investment_memo.py     → static SYMBOL_BRIEFS (user-specific)
├── analysis/benchmark_comparison.py → weighted 1Y vs Nifty snapshot
└── analysis/performance.py         → CAGR, Sharpe, Sortino, max DD, etc.

Domain / metadata
├── domain/provenance.py            → ClaimType, DataProvenance, staleness
└── backtest/config.py              → BacktestValidationPlan (not executed)

Storage
└── cache/store.py → SQLite: snapshots, LTP cache, daily candles, recommendation history

Reporting
├── report/deep_renderer.py → markdown
└── report/renderer.py      → write .md + .json

Security
├── secrets.py + macOS Keychain for Groww credentials
└── auth.py → Groww token (approval/TOTP), secret redaction
```

---

## 4. Analysis pipeline — step by step

Each `grow-assistant analyze` run executes:

### Stage A — Holdings (`ingest_holdings`)

1. **Online:** `GrowwClient.get_holdings()` + positions → save SQLite snapshot
2. **Fallback:** Groww CSV/XLSX import (`stocks.json`) or last cached snapshot
3. **Offline:** Import file or cache only; no live Groww call
4. Returns `HoldingsStageResult` + `IngestionResult` (source status per provider)

### Stage B — Prices (`ingest_prices`)

1. **Yahoo Finance** (`YahooFinanceProvider`): batched LTP for NSE symbols + benchmark (NIFTY → `^NSEI`)
2. **Groww LTP overlay** when API available (online + Groww ok)
3. **Fallback:** if Yahoo missing a symbol → use user's **average buy price** (warns in report)
4. Sync **2Y daily candles** to SQLite for indicator calculation
5. `get_full_data()` per symbol for 1Y/3Y return, 52w high/low, vol, MA, RSI, MACD, ATR

### Stage C — Features & position metrics (`build_position_metrics`)

From cached OHLCV per symbol:

- `ma50`, `ma200`, `trend` (uptrend / downtrend / mixed / insufficient_data)
- `volatility_30d` (annualized decimal)
- `max_drawdown_1y` (%)
- `rsi14`, `macd`, `macd_signal`, `atr14`

Portfolio weights and unrealized P&L from qty × last_price vs avg buy.

### Stage D — Recommendations (`rank_recommendations`)

Rule engine (not ML):

| Trigger | Action |
|---------|--------|
| Weight > `MAX_SINGLE_STOCK_WEIGHT` (default 15%) | rebalance-candidate (with 30-day cooldown) |
| Price below MA50 and MA200 | monitor |
| Unrealized gain > 100% | research |
| 30d vol > 40% | monitor |
| Each rec includes **evidence** + **counterpoints** |

### Stage E — Ancillary (`ingest_ancillary`)

- **MF:** `MFApiClient.analyze_holdings()` from `mutual_funds.json`
- **News:** Google News RSS for top 6 symbols (if `FETCH_NEWS=true`)

### Stage F — Deep analysis (`run_deep_analysis`)

Combines stocks + MF:

- Sector/category weights
- Diversification score 0–100 (concentration, MF overlap, holding count)
- Strategy buckets: keep / trim / monitor / consider-buy suggestions
- Benchmark 1Y return from Yahoo (context only)

### Stage G — Investment memo (`build_investment_memo`)

**User-specific static briefs** in `SYMBOL_BRIEFS` dict (HDFCBANK, ETERNAL, SWIGGY, RELIANCE, etc.):

- 90-day process steps (not trade orders)
- Per-stock thesis: why / do / don't / watch
- MF role classification (core vs satellite)
- Claim type in provenance: `llm_interpretation` (maintained in Cursor, not live LLM API)

### Stage H — Benchmark & performance

- **`benchmark_comparison`:** portfolio weighted 1Y stock return vs Nifty 1Y — **snapshot using today's weights**, explicitly NOT a backtest; includes counterpoints (survivorship, timing of buys)
- **`benchmark_performance`:** Sharpe, max DD, CAGR, vol on Nifty daily closes from SQLite/Yahoo

### Stage I — Metadata & output

- **`provenance`:** claim legend + per-field source records + disclaimer
- **`ingestion`:** holdings/prices/ancillary source status (ok/partial/failed/skipped)
- **`data_warnings`:** stale LTP, Yahoo fallbacks, Groww failures
- Write `reports/YYYY-MM-DD.md` + `.json`

---

## 5. Report JSON schema (key top-level keys)

```json
{
  "generated_at": "ISO8601 IST",
  "snapshot_id": 10,
  "portfolio": {
    "total_value", "total_cost", "total_unrealized_pnl", "total_unrealized_pnl_pct",
    "positions": [{
      "trading_symbol", "quantity", "average_price", "last_price",
      "market_value", "cost_basis", "unrealized_pnl", "unrealized_pnl_pct", "weight_pct",
      "ma50", "ma200", "trend", "volatility_30d", "max_drawdown_1y",
      "rsi14", "macd", "macd_signal", "atr14",
      "bought_price", "sell_price"
    }]
  },
  "deep_analysis": { "combined_*", "sector_weights", "stock_market_data", "mutual_funds", "news", "strategy" },
  "investment_memo": { "headline", "this_quarter", "stock_theses", "mf_roles", "rules", "sources_note" },
  "recommendations": [{ "symbol", "action", "rank", "evidence", "counterpoints" }],
  "benchmark_comparison": {
    "benchmark_symbol", "benchmark_return_1y_pct",
    "portfolio_weighted_return_1y_pct", "alpha_vs_benchmark_pct",
    "coverage_pct", "notes", "counterpoints", "claim_type": "calculated"
  },
  "benchmark_performance": { "sharpe_ratio", "max_drawdown_pct", "cagr_pct", ... },
  "ingestion": { "holdings", "prices", "ancillary" },
  "provenance": { "claim_legend", "records", "disclaimer" },
  "backtest_validation_plan": { "status": "planned", "engine": "not_implemented", ... },
  "data_warnings": [],
  "analysis_method": [],
  "checklist": []
}
```

---

## 6. Web dashboard (UI)

FastAPI + static HTML/JS at port 8765.

| Tab | Shows |
|-----|-------|
| **Plan** | Investment memo headline + quarterly steps |
| **Stocks** | Holdings table + trend/RSI columns + suggestions |
| **Mutual Funds** | MF NAV P&L + suggestions |
| **Full memo** | Stock theses + MF roles + house rules |
| **Research** *(added recently)* | Benchmark vs Nifty, Nifty risk metrics, technical table (RSI/MACD/ATR), data quality/ingestion, news, rule flags |

API: `GET /api/report/latest`, `POST /api/analyze`, `POST /api/import`

**Note:** UI reads from JSON reports. User must **Run Analysis** + hard refresh to see new fields.

---

## 7. Changes implemented in recent development sessions

### Phase 0 — Foundations

| Addition | Path | What it does |
|----------|------|--------------|
| Claim types & provenance | `domain/provenance.py` | `reported` / `calculated` / `model_prediction` / `llm_interpretation` |
| Staleness warnings | `domain/provenance.py` + `cache/store.get_ltp_fetched_at()` | Warn if cached prices > 24h old |
| Performance metrics | `analysis/performance.py` | CAGR, Sharpe, Sortino, Calmar, win rate, profit factor |
| Backtest plan schema | `backtest/config.py` | Friction defaults, walk-forward windows, bias controls — **not executed** |
| Tests | `tests/test_performance.py`, `test_api_resilience.py`, `test_missing_values.py`, `test_provenance.py` | 59 tests total, all passing |

### Phase 1 — Layer extraction

| Addition | Path | What it does |
|----------|------|--------------|
| Unified indicators | `features/indicators.py` | Single source for MA, vol, RSI, MACD, ATR; removed duplicate math in `yahoo_finance.py` |
| Ingestion results | `ingestion/result.py` | Per-source ok/partial/failed/skipped |
| Pipeline stages | `pipeline/stages.py` | `ingest_holdings` → `ingest_prices` → `ingest_ancillary` |
| Pipeline runner | `pipeline/runner.py` | Orchestrates analysis + report assembly |
| Benchmark comparison | `analysis/benchmark_comparison.py` | Weighted 1Y portfolio vs Nifty with counterpoints |
| Extended position metrics | `analysis/metrics.py` | Added rsi14, macd, macd_signal, atr14 to each position |

### UI / reporting updates

| Addition | Path | What it does |
|----------|------|--------------|
| Research tab | `web/static/app.js`, `index.html` | Surfaces benchmark, technicals, ingestion, news |
| Markdown research section | `report/deep_renderer.py` | Benchmark block + technical indicator table in .md reports |
| Architecture doc | `docs/ARCHITECTURE_AND_ROADMAP.md` | Full roadmap, gaps, security review, backtest plan |

---

## 8. What is NOT implemented yet (important for reviewer)

1. **Runtime LLM** — memo text is static Python dict, not API-driven synthesis with citations
2. **Backtest engine** — only config schema; no vectorbt/backtrader integration
3. **Fundamentals** — `providers/base.py` is a stub; no FMP/Finnhub/SEC data
4. **Walk-forward validation** — documented, not coded
5. **Corporate action adjustments** — raw Yahoo closes
6. **NSE holiday calendar** — scheduler uses weekdays only
7. **Per-field provenance** — report-level block only, not every metric
8. **Paper trading mode** — intentionally absent
9. **pandas-ta** — pure Python indicators; optional pandas-ta hook exists but unused
10. **Authentication on web UI** — localhost only, no API token

---

## 9. Data sources & limitations

| Data | Source | Fallback | Risk |
|------|--------|----------|------|
| Holdings qty/avg buy | Groww API or import | SQLite cache | Groww daily approval required |
| Stock LTP | Yahoo Finance | Groww LTP → avg buy price | Yahoo unofficial; stale quotes masked by avg-buy fallback |
| Historical OHLCV | Yahoo 2Y daily | SQLite cache | No split adjustment guarantee |
| MF NAV | MFApi.in | None | Manual `mutual_funds.json` required |
| News | Google News RSS | Skipped if offline | Headlines unverified |
| Benchmark | NIFTY via Yahoo `^NSEI` | — | Index ≠ user's blended portfolio |

---

## 10. Security & privacy

- Groww API key/secret in **macOS Keychain** (not plain `.env`)
- Read-only — no order endpoints
- Portfolio data in gitignored `data/` and `reports/`
- Web dashboard binds locally; holdings visible to anyone on same machine if bound to 0.0.0.0
- **Repo is public** for AI review — ensure no secrets committed (`.env` gitignored)

---

## 11. Configuration (`.env`)

```
MAX_SINGLE_STOCK_WEIGHT=15
MAX_SECTOR_WEIGHT=30
REBALANCE_COOLDOWN_DAYS=30
BENCHMARK_SYMBOL=NIFTY
FETCH_NEWS=true
STOCKS_PATH=./stocks.json
MUTUAL_FUNDS_PATH=./mutual_funds.json
```

---

## 12. How to run & verify

```bash
pip install -e ".[dev]"
grow-assistant secrets set          # Groww credentials → Keychain
grow-assistant verify-auth
grow-assistant analyze              # or --offline
grow-assistant dashboard            # http://127.0.0.1:8765 → Research tab
pytest                              # 59 tests
```

---

## 13. Example user portfolio context (why memo is personalized)

The investment memo (`investment_memo.py`) contains **hard-coded briefs** for this user's actual holdings, e.g.:

- **HDFCBANK** ~45% of book → "stop adding; route new SIPs to index/flexi core"
- **ETERNAL** (ex-Zomato) satellite winner → cap size after strong 2026 run
- **SWIGGY + ETERNAL** overlap → don't hold two internet delivery names
- Multiple mid-cap MFs → consolidate to one mid-cap SIP

Reviewer should assess whether static briefs should become **evidence-linked dynamic research cards**.

---

## 14. Known technical debt

1. `pipeline/runner.py` still assembles report payload inline (could be `presentation/` layer)
2. Volatility units inconsistent in places (decimal in metrics vs % in yahoo `StockMarketData.volatility_30d`)
3. Benchmark comparison uses **current weights × historical 1Y returns** — statistically misleading if labeled "alpha"
4. Duplicate `get_full_data()` Yahoo calls per symbol (price stage + market data load)
5. Sector map is static dict — new tickers → "Other"
6. Web UI does not render `backtest_validation_plan` or full `provenance.records`

---

## 15. Planned next phases (from roadmap)

| Phase | Focus |
|-------|-------|
| **2** | Per-field provenance, data quality score, NSE holidays, optional FMP adapter |
| **3** | LLM synthesizer adapter — cites structured JSON only, never computes numbers |
| **4** | Backtest MVP (concentration-trim rule vs buy-and-hold, walk-forward, friction model) |
| **5** | Paper trading (double opt-in, hard caps) — future only |

**User priority:** Strengthen **research/analysis output** (dynamic evidence, fundamentals, peer comparison) — not infra or trading.

---

## 16. Questions for the reviewing AI

Please review this system and answer:

1. **Architecture:** Is the ingestion → features → analysis → presentation split sound? What's the highest-impact refactor with minimal scope?

2. **Research quality:** Is `benchmark_comparison` presented honestly enough? What statistical flaws remain and how should we fix them without a full backtest?

3. **Indicators:** Are our pure-Python RSI/MACD/ATR implementations sufficient, or should we mandate pandas-ta/TA-Lib with golden-file tests?

4. **Investment memo:** Static `SYMBOL_BRIEFS` vs runtime LLM with provenance — what's the safest hybrid for a personal tool?

5. **Data risk:** Yahoo + avg-buy fallback — what guardrails prevent acting on bad prices?

6. **Backtest priority:** Given a single-user long-term portfolio, should we build backtest engine next or fundamentals + research cards first?

7. **Security:** Public repo + local dashboard — any concerns beyond standard "don't commit secrets"?

8. **Missing metrics:** For Indian long-term equity + MF portfolio, what analysis is conspicuously absent?

9. **UI/UX:** Does the Research tab cover the right surface area? What's missing for decision support without becoming financial advice?

10. **Top 5 prioritized improvements** with effort estimate (S/M/L) for a solo developer.

---

## 17. File index (for code review)

```
src/grow_trade_assistant/
├── cli.py, config.py, scheduler.py
├── auth.py, secrets.py, groww_client.py, groww_import.py
├── pipeline/runner.py, pipeline/stages.py
├── features/indicators.py
├── ingestion/result.py
├── analysis/metrics.py, recommendations.py, deep_analysis.py,
│   investment_memo.py, benchmark_comparison.py, performance.py
├── domain/provenance.py
├── backtest/config.py
├── providers/yahoo_finance.py, mfapi.py, news.py, base.py
├── cache/store.py
├── report/deep_renderer.py, renderer.py
└── web/app.py, web/static/{index.html,app.js,style.css}

docs/ARCHITECTURE_AND_ROADMAP.md   — detailed roadmap
docs/AI_REVIEW_BRIEF.md            — this file

tests/                             — 59 pytest tests
reports/YYYY-MM-DD.json            — sample output (user portfolio)
```

---

## 18. Prompt template for external AI

Copy below into your review session:

---

**You are reviewing an open-source personal portfolio analysis tool for Indian markets.**

Repository: https://github.com/DakshMeghawat/grow-trade-assistant

Read the full brief at `docs/AI_REVIEW_BRIEF.md` in the repo (or the pasted content above).

Constraints:
- Read-only, education only, no live trading
- Deterministic math for indicators; LLM only for narrative (currently static briefs)
- User cares most about **research/analysis quality**, not infrastructure polish

Deliver:
1. Critical flaws (data integrity, misleading metrics, security)
2. Research/analysis gaps vs best practice
3. Top 5 improvements ranked by impact/effort
4. Specific code-level suggestions (file + function where possible)
5. Whether benchmark_comparison and technical indicators are trustworthy enough to show a retail investor

Be direct. Assume the user will implement your top suggestions.

---

*Generated: 2026-08-20. Repo visibility: public. Tests: 59 passing.*
