from __future__ import annotations

from typing import Any

from grow_trade_assistant.analysis.metrics import PortfolioSummary, format_inr
from grow_trade_assistant.providers.mfapi import MutualFundHolding


# Cursor-agent briefs (Aug 2026). Not live LLM. Review-only education.
SYMBOL_BRIEFS: dict[str, dict[str, str]] = {
    "HDFCBANK": {
        "stance": "CORE — do not panic-sell; do not add this quarter",
        "why": (
            "Largest private bank, still the valuation anchor for Indian banks. "
            "Aug 2026: stock near a 52-week low (~₹715) after a weak year; RBI allowed LIC to raise stake to 9.99%. "
            "Street story is NIM recovery as high-cost merger borrowings roll off over ~2 years — not a 2-week bounce. "
            "Broker notes still skew Buy with long-dated targets; that is their view, not a guarantee."
        ),
        "do": "Keep the holding if your horizon is 5+ years. Put all *new* SIPs into the index/flexi core until HDFC is under ~15% of *total* portfolio (stocks+MF).",
        "dont": "Do not average down just because it looks cheap vs 2025. Size is the problem, not the brand.",
        "watch": "Next 2–3 earnings: NIM/CASA, deposit growth, credit cost. LIC buying is a vote, not a floor.",
    },
    "ETERNAL": {
        "stance": "SATELLITE winner — cap the size",
        "why": (
            "Eternal (ex-Zomato) is food delivery + Blinkit quick commerce. "
            "Mid-2026 rally (~+30–50% off March lows) is Blinkit-led. Q1 FY27: revenue jumped, profit still thin "
            "and can fall QoQ on tax/opex. Screener-style P/E is extreme — you are paying for growth, not current earnings."
        ),
        "do": "Hold a defined satellite (suggest ≤8–10% of total). Book nothing in panic; also do not add after a sharp 2-month squeeze.",
        "dont": "Do not treat this like HDFC (a compounding bank). Internet + q-comm can give back a year of gains in a quarter.",
        "watch": "Blinkit store economics, competitive intensity vs Swiggy Instamart, cash burn vs guidance.",
    },
    "SWIGGY": {
        "stance": "TINY satellite — overlap with Eternal",
        "why": "Same India food + quick-commerce war as Eternal, much smaller line, already ~10–15% below your buy, high volatility.",
        "do": "Either keep as a <2% 'ticket' or exit if you only want one internet name. Do not SIP both Swiggy and Eternal.",
        "dont": "Do not average down to 'make it matter'. That turns a small mistake into a thesis.",
        "watch": "Instamart vs Blinkit metrics; dilution/fundraising headlines.",
    },
    "RELIANCE": {
        "stance": "CORE hold — no urgency",
        "why": "Conglomerate: oil-to-chemicals, retail, Jio. Your P&L is roughly flat. Trend mixed vs 200-day average — noise, not a thesis change by itself.",
        "do": "Hold as a long-term India compounder if you understand the three engines. New money still better in the Total Market / PPFAS core than more Reliance until weights rebalance.",
        "dont": "Do not trade Jio/retail rumours. Do not let it quietly become a second HDFC-sized line.",
        "watch": "Retail + digital cash flows vs capex; oil cycle is the noisy part.",
    },
    "TATAPOWER": {
        "stance": "KEEP small utilities sleeve",
        "why": "Power + renewables. Your line is modest (~3% total). Policy/tariff and execution drive it more than a week's LTP.",
        "do": "Hold if you want India energy-transition exposure. Size is already fine.",
        "dont": "Do not pile in on one green headline.",
        "watch": "Renewable project wins, leverage, thermal vs clean mix.",
    },
    "VBL": {
        "stance": "KEEP small consumer sleeve",
        "why": "Varun Beverages is a bottler/consumer compounder, not a 'story stock'. Small weight, mild mark-to-market loss — ignore unless thesis (franchise, volumes) breaks.",
        "do": "Hold. Optional SIP only if consumer staples is a deliberate sleeve.",
        "dont": "Do not sell because of a 3–5% dip.",
        "watch": "Volume growth, territory expansion, input costs.",
    },
}


def build_investment_memo(
    summary: PortfolioSummary,
    mf_holdings: list[MutualFundHolding],
    combined: float,
    stocks_cost: float,
    mf_cost: float,
    mf_value: float,
) -> dict[str, Any]:
    """Actionable 90-day memo. Education only — not advice or orders."""
    positions = sorted(summary.positions, key=lambda p: p.market_value, reverse=True)
    mf_sorted = sorted(mf_holdings, key=lambda m: m.market_value, reverse=True)

    this_quarter: list[dict[str, str]] = []
    theses: list[dict[str, str]] = []

    hdfc = next((p for p in positions if p.trading_symbol == "HDFCBANK"), None)
    eternal = next((p for p in positions if p.trading_symbol == "ETERNAL"), None)
    swiggy = next((p for p in positions if p.trading_symbol == "SWIGGY"), None)

    if hdfc and combined:
        w = hdfc.market_value / combined * 100
        this_quarter.append({
            "priority": "1",
            "title": "Stop adding to HDFC Bank until it is a smaller slice",
            "detail": (
                f"Bought ~{format_inr(hdfc.average_price)}, sell-today ~{format_inr(hdfc.last_price)}, "
                f"invested {format_inr(hdfc.cost_basis)} vs {format_inr(hdfc.market_value)} now "
                f"({hdfc.unrealized_pnl_pct:+.1f}%). That is {w:.1f}% of your *entire* book "
                f"(and {hdfc.weight_pct:.0f}% of direct stocks). "
                "Aug 2026 tape is weak (near 52-week lows) while the 2-year story is NIM/funding-cost recovery. "
                "Process: keep the shares if horizon is long; route every new rupee to Total Market / PPFAS until HDFC < 15% of total."
            ),
        })

    mid_names = [m.name for m in mf_sorted if "mid" in (m.category + m.name).lower()]
    if len(mid_names) >= 2:
        this_quarter.append({
            "priority": "2",
            "title": "Run only one dedicated mid-cap SIP",
            "detail": (
                "You hold more than one mid-cap engine (Nippon Growth Mid Cap + Motilal Midcap). "
                "Style differs from PPFAS (global quality/flexi) but two mid-caps stack the same risk bucket. "
                "Pick one as the satellite; pause SIP on the other for 90 days. Do not redeem in a huff."
            ),
        })

    this_quarter.append({
        "priority": "3",
        "title": "All fresh SIPs → core funds, not more single stocks",
        "detail": (
            f"MF is already {mf_value / combined * 100 if combined else 0:.0f}% of the book "
            f"(invested {format_inr(mf_cost)} → {format_inr(mf_value)}). That is the useful part vs Groww's stock screen. "
            "Groww Nifty Total Market + Parag Parikh Flexi Cap are the core. JM Flexi is a third flexi — treat it as optional, not a fourth SIP."
        ),
    })

    if eternal and combined and eternal.unrealized_pnl_pct > 20:
        w = eternal.market_value / combined * 100
        this_quarter.append({
            "priority": "4",
            "title": "Cap Eternal (Zomato) — you already made the easy money this year",
            "detail": (
                f"Bought ~{format_inr(eternal.average_price)}, sell-today ~{format_inr(eternal.last_price)}, "
                f"P&L {eternal.unrealized_pnl_pct:+.1f}%, {w:.1f}% of total. "
                "Blinkit-led rerating + still-rich multiples. Hold the winner; do not add. "
                "If it crosses ~10% of total, trim back to 7–8% over weeks, not one panic click."
            ),
        })

    if swiggy and eternal:
        this_quarter.append({
            "priority": "5",
            "title": "Do not fight the same war twice (Swiggy + Eternal)",
            "detail": (
                f"Swiggy is only {format_inr(swiggy.market_value)} and {swiggy.unrealized_pnl_pct:+.1f}% vs buy. "
                "Same industry as Eternal. Either keep it as a tiny ticket or consolidate into one internet name. No averaging."
            ),
        })

    for p in positions:
        brief = SYMBOL_BRIEFS.get(p.trading_symbol)
        if not brief:
            w = (p.market_value / combined * 100) if combined else p.weight_pct
            theses.append({
                "name": p.trading_symbol,
                "stance": "HOLD pending a written thesis",
                "bought": format_inr(p.average_price),
                "sell_today": format_inr(p.last_price),
                "invested": format_inr(p.cost_basis),
                "current": format_inr(p.market_value),
                "pnl": f"{format_inr(p.unrealized_pnl)} ({p.unrealized_pnl_pct:+.1f}%)",
                "why": f"{w:.1f}% of total. No in-house brief yet — write why you own it in one sentence or it is a leftover.",
                "do": "Keep only with a 5-year reason.",
                "dont": "Do not add on boredom.",
                "watch": "Your own thesis, not the daily LTP.",
            })
            continue
        theses.append({
            "name": p.trading_symbol,
            "stance": brief["stance"],
            "bought": format_inr(p.average_price),
            "sell_today": format_inr(p.last_price),
            "invested": format_inr(p.cost_basis),
            "current": format_inr(p.market_value),
            "pnl": f"{format_inr(p.unrealized_pnl)} ({p.unrealized_pnl_pct:+.1f}%)",
            "why": brief["why"],
            "do": brief["do"],
            "dont": brief["dont"],
            "watch": brief["watch"],
        })

    mf_plan = []
    for m in mf_sorted:
        name_l = m.name.lower()
        if "total market" in name_l or "nifty" in name_l:
            role = "CORE index — keep SIP"
        elif "parag parikh" in name_l or "ppfas" in name_l:
            role = "CORE flexi (global + India quality) — keep SIP"
        elif "mid" in name_l:
            role = "SATELLITE mid-cap — one SIP only across all mid-caps"
        elif "small" in name_l:
            role = "SATELLITE small-cap — high vol; SIP only if 7+ year horizon"
        elif "flexi" in name_l:
            role = "Extra flexi — optional; don't SIP three flexis"
        else:
            role = "Classify as core vs satellite"
        mf_plan.append({
            "name": m.name,
            "role": role,
            "invested": format_inr(m.cost_basis),
            "current": format_inr(m.market_value),
            "pnl": f"{m.unrealized_pnl_pct:+.1f}%",
            "nav_bought": f"₹{m.avg_nav:,.2f}",
            "nav_today": f"₹{m.current_nav:,.2f}",
        })

    verdict = (
        "Your edge vs Groww is not another P&L table — it is a written plan: "
        "core SIPs on, concentrated stock SIPs off, one mid-cap satellite, internet names capped. "
        "Numbers below only exist to size that plan."
    )

    return {
        "headline": verdict,
        "this_quarter": this_quarter,
        "stock_theses": theses,
        "mf_roles": mf_plan,
        "rules": [
            "Horizon 5+ years unless you explicitly labelled a line as a trade (you have not).",
            "New money → core MF first (Total Market / PPFAS).",
            "No second name in the same war (Swiggy vs Eternal) without cutting the first.",
            "Trim on size and thesis, not on a red day.",
            "This memo is education. Verify filings and NAVs. Not SEBI-registered advice. No orders.",
        ],
        "sources_note": (
            "Prices: Yahoo NSE / MFApi NAV. Context: public news Aug 2026 (HDFC near 52w low + LIC stake cap; "
            "Eternal/Blinkit growth vs rich multiples). Not an LLM API inside the button — briefs are maintained with the agent in Cursor."
        ),
    }
