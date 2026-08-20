# Grow Trade Assistant

Read-only portfolio analysis tool for **long-term Indian equity investing** via the [Groww Trading API](https://groww.in/trade-api/docs/curl).

It pulls your holdings, fetches market data efficiently (batched + cached), computes portfolio metrics, and produces an **impactful learning report** with review-only recommendations. It never places orders.

## Quick start

```bash
cd ~/Projects/grow-trade-assistant
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Configure settings (non-secret only)
cp .env.example .env

# Store credentials in macOS Keychain (encrypted — NOT in .env)
grow-assistant secrets set

# Verify authentication
grow-assistant verify-auth

# Run analysis now
grow-assistant analyze
```

Reports are written to `reports/YYYY-MM-DD.md` and `reports/YYYY-MM-DD.json`.

## Where to store your API key and secret (secure)

**Do not paste credentials in `.env`.** Plain `.env` files are readable by anyone with access to your laptop.

Instead, use **macOS Keychain** — encrypted at rest, managed by the OS:

```bash
grow-assistant secrets set
```

You'll be prompted for your API key and secret (input is hidden). They are stored in Keychain, not as plain text on disk.

| Command | What it does |
|---------|--------------|
| `grow-assistant secrets set` | Store key + secret in Keychain |
| `grow-assistant secrets status` | Show what's stored (masked) |
| `grow-assistant secrets migrate` | Move credentials from `.env` → Keychain, then scrub `.env` |
| `grow-assistant secrets scrub-env` | Remove secret lines from `.env` |
| `grow-assistant secrets delete` | Remove credentials from Keychain |

**If you already pasted keys in `.env`**, migrate them now:

```bash
grow-assistant secrets migrate
```

This copies credentials to Keychain and removes them from `.env`.

### Extra laptop security (recommended)

1. **Enable FileVault** (System Settings → Privacy & Security → FileVault) — encrypts your entire disk
2. **Use a strong login password** — Keychain is unlocked with your Mac login
3. **Lock your Mac** when away (Control+Command+Q)
4. **Never commit** `.env` or share credentials in chat

`.env` is only for non-secret settings (guardrails, schedule time, paths). See `.env.example`.

**Never** paste credentials in source code, chat, logs, or reports.

## Daily approval (key + secret flow)

Groww requires you to approve your API key each trading day:

1. Go to [Groww Cloud API Keys](https://groww.in/trade-api)
2. Approve today's session for your key
3. Run `grow-assistant verify-auth` to confirm
4. Run `grow-assistant analyze`

If auth fails, the tool prints a clear message pointing you to the approval page.

## Commands

| Command | Description |
|---------|-------------|
| `grow-assistant dashboard` | **Web UI** — open portfolio dashboard in browser |
| `grow-assistant analyze` | **Deep analysis report** — live prices, history, news, strategy |
| `grow-assistant analyze --offline` | Use cached snapshot only |
| `grow-assistant secrets set-token --file ./groww-token.txt` | Store daily access token |
| `grow-assistant schedule` | Run EOD reports on Indian market weekdays |

## Web dashboard

Launch a local UI to view everything in one place:

```bash
grow-assistant dashboard
```

Open **http://127.0.0.1:8765** in your browser.

The dashboard shows:
- Portfolio value, P&L, diversification score
- Sector and holdings charts
- Action plan (Keep / Trim / Monitor / Consider Adding)
- Mutual fund holdings
- News headlines
- Strategy verdict and reallocation roadmap
- **Run Analysis** button to refresh data live

## How market data works

```
Groww API  →  batched LTP (up to 50 symbols/call)
           →  daily historical candles (cached in SQLite)
           →  local cache avoids refetching unchanged data
```

- **Live prices:** fetched at report time via batched LTP calls
- **Trend analysis:** 50/200-day moving averages from cached daily candles
- **Rate limits:** batched requests stay well under Groww's 300/min live-data limit
- **Reliability:** retries on transient errors; secrets redacted from logs

Data is stored in `data/portfolio.db` (gitignored).

## Report structure

Each report includes:

1. **Portfolio health** — total value, P&L, per-holding weights and trends
2. **What changed** — vs previous snapshot (new/removed holdings, quantity/price moves)
3. **Key risks** — concentration warnings when a stock exceeds your limit
4. **Recommendations** — ranked `keep`, `monitor`, `research`, `rebalance-candidate` with evidence and counterpoints
5. **Learning note** — one metric explained in plain language
6. **Manual checklist** — questions to ask before acting

## Guardrails (configurable in `.env`)

| Setting | Default | Meaning |
|---------|---------|---------|
| `MAX_SINGLE_STOCK_WEIGHT` | 15% | Flag if one stock exceeds this |
| `MAX_SECTOR_WEIGHT` | 30% | Reserved for future sector data |
| `MIN_CASH_BUFFER_PERCENT` | 5% | Reserved for future cash tracking |
| `REBALANCE_COOLDOWN_DAYS` | 30 | Don't repeat rebalance suggestions too often |

## Scheduling

```bash
grow-assistant schedule
```

Runs analysis at `SCHEDULE_TIME` (default 18:00 IST) on weekdays. For unattended 24/7 operation, run this in `tmux`, `screen`, or as a launchd/cron job.

While Cursor is open, you can also ask the agent to run `grow-assistant analyze` on a cadence.

## Limitations (v1)

- Indian CASH (equity delivery) segment only
- No order placement — review and manual execution only
- No foreign stocks (future: separate broker adapter)
- Fundamentals are placeholders until a licensed provider is added
- NSE holidays not modeled in scheduler (weekdays only)

## Development

```bash
pip install -e ".[dev]"
pytest
```

## Disclaimer

This tool is for **learning and research**. It is not financial advice. All investment decisions are yours.
