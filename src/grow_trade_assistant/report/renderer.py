from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Callable


def render_markdown_report(
    payload: dict[str, Any],
    format_inr: Callable[[float], str],
) -> str:
    portfolio = payload["portfolio"]
    lines = [
        f"# Portfolio Report — {payload['generated_at'][:10]}",
        "",
        "> **Disclaimer:** This report is for learning and research only. "
        "It is not financial advice. All decisions are yours.",
        "",
        f"**Snapshot ID:** {payload['snapshot_id']}  ",
        f"**Generated:** {payload['generated_at']}",
        "",
        "## Portfolio Health",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Total value | {format_inr(portfolio['total_value'])} |",
        f"| Total cost | {format_inr(portfolio['total_cost'])} |",
        f"| Unrealized P&L | {format_inr(portfolio['total_unrealized_pnl'])} ({portfolio['total_unrealized_pnl_pct']:+.1f}%) |",
        "",
        "### Holdings",
        "",
        "| Symbol | Qty | LTP | Value | Weight | P&L | Trend |",
        "|--------|-----|-----|-------|--------|-----|-------|",
    ]

    for p in portfolio["positions"]:
        trend = p.get("trend") or "—"
        lines.append(
            f"| {p['trading_symbol']} | {p['quantity']:g} | "
            f"{format_inr(p['last_price'])} | {format_inr(p['market_value'])} | "
            f"{p['weight_pct']:.1f}% | {p['unrealized_pnl_pct']:+.1f}% | {trend} |"
        )

    lines.extend(["", "## What Changed Since Last Report", ""])
    for change in payload["changes_since_last"]:
        lines.append(f"- {change}")

    if payload.get("data_warnings"):
        lines.extend(["", "## Data Quality Notes", ""])
        for w in payload["data_warnings"]:
            lines.append(f"- {w}")

    if payload["concentration_warnings"]:
        lines.extend(["", "## Key Risks", ""])
        for w in payload["concentration_warnings"]:
            lines.append(f"- {w}")

    lines.extend(["", "## Recommendations (Review Only)", ""])
    for rec in payload["recommendations"]:
        if rec["action"] == "keep":
            continue
        lines.append(f"### {rec['symbol']} — `{rec['action']}`")
        lines.append("")
        lines.append("**Evidence:**")
        for e in rec["evidence"]:
            lines.append(f"- {e}")
        lines.append("")
        lines.append("**Why this could be wrong:**")
        for c in rec["counterpoints"]:
            lines.append(f"- {c}")
        lines.append("")

    lines.extend(["## Learning Note", "", payload["learning_note"], ""])
    lines.extend(["## Data Sources & Limitations", ""])
    sources = payload["data_sources"]
    lines.append(f"- Broker: {sources['broker']}")
    lines.append(f"- Fundamentals: {sources['fundamentals']}")
    for lim in sources["limitations"]:
        lines.append(f"- {lim}")

    lines.extend(["", "## Manual Decision Checklist", ""])
    for item in payload["checklist"]:
        lines.append(f"- [ ] {item}")

    lines.append("")
    return "\n".join(lines)


def write_reports(
    reports_dir: Path,
    payload: dict[str, Any],
    markdown: str,
) -> dict[str, Path]:
    date_str = payload["generated_at"][:10]
    md_path = reports_dir / f"{date_str}.md"
    json_path = reports_dir / f"{date_str}.json"

    md_path.write_text(markdown, encoding="utf-8")
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return {"markdown": md_path, "json": json_path}
