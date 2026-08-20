from __future__ import annotations

from typing import Any, Callable


def _pct(value: float | None) -> str:
    if value is None or (isinstance(value, float) and value != value):
        return "—"
    return f"{value:+.1f}%"


def _suggestion_sections(suggestions: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    buckets = {"trim": [], "monitor": [], "keep": [], "consider": []}
    for s in suggestions:
        buckets.setdefault(s.get("bucket", "keep"), []).append(s)
    return buckets


def render_deep_markdown(payload: dict[str, Any], format_inr: Callable[[float], str]) -> str:
    """Render invested-vs-current analysis and a structured suggestion report."""
    lines: list[str] = []
    deep = payload.get("deep_analysis", {})
    strategy = deep.get("strategy", {})
    portfolio = payload["portfolio"]
    suggestions = strategy.get("suggestions") or []

    stocks_cost = deep.get("stocks_cost", portfolio.get("total_cost", 0) or 0)
    mf_cost = deep.get("mf_cost", 0) or 0
    combined_cost = deep.get("combined_cost", stocks_cost + mf_cost) or 0
    combined_value = deep.get("combined_value", portfolio.get("total_value", 0)) or 0
    stocks_value = deep.get("stocks_value", portfolio.get("total_value", 0)) or 0
    mf_value = deep.get("mf_value", 0) or 0
    combined_pnl = deep.get("combined_pnl", combined_value - combined_cost)
    combined_pnl_pct = deep.get("combined_pnl_pct")
    if combined_pnl_pct is None and combined_cost:
        combined_pnl_pct = combined_pnl / combined_cost * 100
    stock_pnl = portfolio.get("total_unrealized_pnl", stocks_value - stocks_cost)
    stock_pnl_pct = portfolio.get("total_unrealized_pnl_pct", 0)
    mf_pnl = mf_value - mf_cost
    mf_pnl_pct = (mf_pnl / mf_cost * 100) if mf_cost else 0.0

    memo = payload.get("investment_memo") or {}

    lines.extend([
        f"# Investment memo — {payload['generated_at'][:10]}",
        "",
        "> Education only. Not financial advice. No orders. Verify on Groww / exchange filings before you act.",
        "",
        f"{memo.get('headline') or strategy.get('headline', '')}",
        "",
        f"| | Invested | If sold / redeemed today | P&L | Mix |",
        f"|--|---------:|-------------------------:|----:|----:|",
        f"| **Total** | {format_inr(combined_cost)} | {format_inr(combined_value)} | {_pct(combined_pnl_pct)} | 100% |",
        f"| Stocks | {format_inr(stocks_cost)} | {format_inr(stocks_value)} | {_pct(stock_pnl_pct)} | {deep.get('stocks_weight_pct', 0):.1f}% |",
        f"| Mutual funds | {format_inr(mf_cost)} | {format_inr(mf_value)} | {_pct(mf_pnl_pct)} | {deep.get('mf_weight_pct', 0):.1f}% |",
        "",
    ])
    if memo.get("this_quarter"):
        lines.extend(["## This quarter (process, not trades)", ""])
        for step in memo["this_quarter"]:
            lines.append(f"### {step.get('priority')}. {step.get('title')}")
            lines.append("")
            lines.append(step.get("detail", ""))
            lines.append("")
    if memo.get("stock_theses"):
        lines.extend(["## Stock theses (bought vs sell-today)", ""])
        for t in memo["stock_theses"]:
            lines.append(f"### {t.get('name')} — {t.get('stance')}")
            lines.append("")
            lines.append(
                f"Bought **{t.get('bought')}** → sell-today **{t.get('sell_today')}** · "
                f"invested {t.get('invested')} → {t.get('current')} · {t.get('pnl')}"
            )
            lines.append("")
            lines.append(f"- **Why it matters:** {t.get('why')}")
            lines.append(f"- **Do:** {t.get('do')}")
            lines.append(f"- **Don't:** {t.get('dont')}")
            lines.append(f"- **Watch:** {t.get('watch')}")
            lines.append("")
    if memo.get("mf_roles"):
        lines.extend(["## Mutual fund roles", ""])
        lines.append("| Fund | Role | Bought NAV | NAV today | Invested | Now | P&L |")
        lines.append("|------|------|------------|-----------|----------|-----|-----|")
        for m in memo["mf_roles"]:
            name = (m.get("name") or "")[:40]
            lines.append(
                f"| {name} | {m.get('role')} | {m.get('nav_bought')} | {m.get('nav_today')} | "
                f"{m.get('invested')} | {m.get('current')} | {m.get('pnl')} |"
            )
        lines.append("")
    if memo.get("rules"):
        lines.extend(["## House rules", ""])
        for r in memo["rules"]:
            lines.append(f"- {r}")
        lines.append("")
    if memo.get("sources_note"):
        lines.extend([f"*{memo['sources_note']}*", ""])

    lines.extend([
        "---",
        "",
        "## Appendix — full numbers",
        "",
    ])
    if deep.get("benchmark_return_1y") is not None:
        lines.append(f"Nifty 1Y (Yahoo, for context only): **{deep['benchmark_return_1y']:+.1f}%**")
        lines.append("")

    lines.extend(["## 2. What looks strong / weak", ""])
    for label, key in [("Strengths", "strengths"), ("Weaknesses", "weaknesses")]:
        items = strategy.get(key, [])
        if not items:
            continue
        lines.append(f"### {label}")
        for item in items:
            lines.append(f"- {item}")
        lines.append("")

    lines.extend([
        "## 3. Suggestion report (review only)",
        "",
        "Each item uses **your invested amount vs today's value**. "
        "Suggestions are about **sizing and process**, not buy/sell orders.",
        "",
    ])
    bucket_titles = [
        ("trim", "Trim / reduce concentration"),
        ("monitor", "Monitor (do not panic-sell)"),
        ("keep", "Keep / continue"),
        ("consider", "Research later (optional)"),
    ]
    grouped = _suggestion_sections(suggestions)
    if not suggestions:
        for title, key in [
            ("KEEP", "actions_keep"),
            ("TRIM / REVIEW", "actions_trim"),
            ("MONITOR", "actions_research"),
            ("CONSIDER", "actions_consider_buy"),
        ]:
            items = strategy.get(key, [])
            if items:
                lines.append(f"### {title}")
                for item in items:
                    lines.append(f"- {item}")
                lines.append("")
    else:
        for bucket, title in bucket_titles:
            items = grouped.get(bucket) or []
            if not items:
                continue
            lines.append(f"### {title}")
            lines.append("")
            for s in items:
                name = s.get("name", "")
                lines.append(f"#### {name}")
                if s.get("asset_type") != "idea":
                    lines.append(
                        f"- **Invested:** {format_inr(s.get('invested', 0))} · "
                        f"**Current:** {format_inr(s.get('current', 0))} · "
                        f"**P&L:** {format_inr(s.get('pnl', 0))} ({_pct(s.get('pnl_pct'))}) · "
                        f"**Weight:** {s.get('weight_pct', 0):.1f}%"
                    )
                lines.append(f"- **Why:** {s.get('why', '')}")
                lines.append(f"- **Suggestion:** {s.get('suggestion', '')}")
                if s.get("counter"):
                    lines.append(f"- **Counterpoint:** {s.get('counter')}")
                lines.append("")

    if strategy.get("reallocation_plan"):
        lines.extend(["### Reallocation roadmap", ""])
        for i, step in enumerate(strategy["reallocation_plan"], 1):
            lines.append(f"{i}. {step}")
        lines.append("")

    lines.extend(["---", "", "## 4. Stocks dashboard — bought price vs sell price (today)", ""])
    lines.extend([
        "| Symbol | Qty | Bought price | Sell price (today) | Invested | If sold today | P&L ₹ | P&L % | Weight |",
        "|--------|-----|--------------|--------------------|----------|---------------|-------|-------|--------|",
    ])
    for p in portfolio["positions"]:
        bought = p.get("bought_price", p.get("average_price", 0))
        sell = p.get("sell_price", p.get("last_price", 0))
        lines.append(
            f"| {p['trading_symbol']} | {p.get('quantity', 0):g} | {format_inr(bought)} | {format_inr(sell)} | "
            f"{format_inr(p.get('cost_basis', 0))} | {format_inr(p['market_value'])} | "
            f"{format_inr(p.get('unrealized_pnl', 0))} | {_pct(p.get('unrealized_pnl_pct'))} | {p['weight_pct']:.1f}% |"
        )
    lines.append("")

    mfs = deep.get("mutual_funds", [])
    if mfs:
        lines.extend([
            "## 5. Mutual funds dashboard — bought NAV vs sell NAV (today)",
            "",
            "| Fund | Units | Bought NAV | Sell NAV (today) | Invested | If redeemed today | P&L ₹ | P&L % | 1Y |",
            "|------|-------|------------|------------------|----------|-------------------|-------|-------|----|",
        ])
        for m in mfs:
            name = (m.get("name") or "")[:42]
            bought = m.get("bought_price", m.get("avg_nav", 0))
            sell = m.get("sell_price", m.get("current_nav", 0))
            lines.append(
                f"| {name} | {m.get('units', 0):g} | ₹{bought:,.2f} | ₹{sell:,.2f} | "
                f"{format_inr(m.get('cost_basis', 0))} | {format_inr(m.get('market_value', 0))} | "
                f"{format_inr(m.get('unrealized_pnl', 0))} | "
                f"{_pct(m.get('unrealized_pnl_pct'))} | {_pct(m.get('return_1y_pct'))} |"
            )
        lines.append("")

    sector_weights = deep.get("sector_weights", {})
    if sector_weights:
        lines.extend(["## 6. Mix by sector / MF category", "", "| Sleeve | Weight of total |", "|--------|-----------------|"])
        for sector, weight in sector_weights.items():
            lines.append(f"| {sector} | {weight:.1f}% |")
        lines.append("")

    news = deep.get("news", {})
    if news:
        lines.extend(["## Headlines (verify independently)", ""])
        for sym, items in news.items():
            if not items:
                continue
            lines.append(f"### {sym}")
            for n in items[:3]:
                lines.append(f"- [{n.get('title', '')}]({n.get('link', '')})")
            lines.append("")

    if payload.get("data_warnings"):
        lines.extend(["## Data notes", ""])
        for w in payload["data_warnings"]:
            lines.append(f"- {w}")
        lines.append("")

    lines.extend(["## Learning note", "", payload.get("learning_note", ""), ""])
    lines.extend(["## Checklist before you act", ""])
    for item in payload.get("checklist", []):
        lines.append(f"- [ ] {item}")

    sources = payload.get("data_sources", {})
    lines.extend(["", "## Sources", ""])
    lines.append(f"- Holdings: {sources.get('broker', 'Groww')}")
    lines.append(f"- Live prices: {sources.get('prices', 'Yahoo Finance')}")
    lines.append(f"- Mutual funds: {sources.get('mutual_funds', 'MFApi.in')}")
    lines.append(f"- News: {sources.get('news', 'Google News RSS')}")
    for lim in sources.get("limitations", []):
        lines.append(f"- {lim}")
    lines.append("")
    return "\n".join(lines)
