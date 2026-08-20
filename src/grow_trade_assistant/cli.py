from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import click

from grow_trade_assistant.auth import generate_checksum, looks_like_access_token
from grow_trade_assistant.config import load_settings
from grow_trade_assistant.pipeline import run_analysis
from grow_trade_assistant.mf_config import (
    add_holding,
    load_mutual_fund_file,
    search_schemes,
)


@click.group()
@click.option("--env-file", type=click.Path(exists=True), default=None, help="Path to .env file")
@click.pass_context
def main(ctx: click.Context, env_file: str | None) -> None:
    """Grow Trade Assistant — read-only portfolio analysis."""
    ctx.ensure_object(dict)
    ctx.obj["env_file"] = env_file


@main.command("analyze")
@click.option("--offline", is_flag=True, help="Use cached data only (no API calls)")
@click.pass_context
def analyze(ctx: click.Context, offline: bool) -> None:
    """Run portfolio analysis now and write a report."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    env_file = ctx.obj.get("env_file")
    try:
        settings = load_settings(env_file, require_groww=not offline)
    except ValueError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)
    try:
        result = run_analysis(settings, offline=offline)
        paths = result.get("report_paths", {})
        deep = result.get("deep_analysis", {})
        click.echo("Analysis complete." + (" (offline)" if offline else ""))
        click.echo(f"  Markdown: {paths.get('markdown')}")
        click.echo(f"  JSON:     {paths.get('json')}")
        combined = deep.get("combined_value")
        if combined is not None:
            click.echo(f"  Invested → current: ₹{deep.get('combined_cost', 0):,.2f} → ₹{combined:,.2f}")
            click.echo(
                f"  P&L: ₹{deep.get('combined_pnl', 0):,.2f} ({deep.get('combined_pnl_pct', 0):+.1f}%)"
            )
            click.echo(
                f"  Stocks: ₹{result['portfolio']['total_value']:,.2f} | MF: ₹{deep.get('mf_value', 0):,.2f}"
            )
        else:
            click.echo(f"  Portfolio value: ₹{result['portfolio']['total_value']:,.2f}")
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)


@main.command("schedule")
@click.pass_context
def schedule(ctx: click.Context) -> None:
    """Run end-of-day analysis on Indian market weekdays."""
    env_file = ctx.obj.get("env_file")
    settings = load_settings(env_file)
    run_scheduled_loop(settings)


@main.command("verify-auth")
@click.pass_context
def verify_auth(ctx: click.Context) -> None:
    """Test Groww authentication without running full analysis."""
    from grow_trade_assistant.auth import GrowwAuth

    env_file = ctx.obj.get("env_file")
    try:
        settings = load_settings(env_file)
    except ValueError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)

    try:
        with GrowwAuth(settings) as auth:
            token = auth.get_access_token()
            click.echo("Authentication successful.")
            click.echo(f"  Token prefix: {token.token[:12]}...")
            if token.expiry:
                click.echo(f"  Expiry: {token.expiry}")
    except Exception as exc:
        click.echo(f"Authentication failed: {exc}", err=True)
        click.echo(
            "\nIf using API key + secret, approve today's session at:\n"
            "  https://groww.in/trade-api\n"
            "Then retry this command."
        )
        sys.exit(1)


@main.group("secrets")
def secrets_group() -> None:
    """Manage Groww credentials in macOS Keychain (encrypted, not plain text)."""


@secrets_group.command("set")
def secrets_set() -> None:
    """Store API key and secret in macOS Keychain (encrypted at rest)."""
    from grow_trade_assistant.secrets import SECRET_FIELDS, backend_name, store_secret

    click.echo("Store Groww credentials in macOS Keychain.")
    click.echo(f"Backend: {backend_name()}")
    click.echo("Values are encrypted by macOS — not stored as plain text on disk.\n")
    click.echo("Get API Key + Secret from: https://groww.in/trade-api → Generate API key")
    click.echo("API Key = short string from that page (NOT the long eyJ... access token)\n")

    api_key = click.prompt("GROWW_API_KEY", hide_input=True)
    if looks_like_access_token(api_key):
        click.echo(
            "\nThat looks like a daily ACCESS TOKEN (starts with eyJ...), not an API key.",
            err=True,
        )
        click.echo(
            "Get your API Key from: https://groww.in/trade-api → Generate API key",
            err=True,
        )
        if not click.confirm("Save it anyway?", default=False):
            raise click.Abort()

    api_secret = click.prompt("GROWW_API_SECRET", hide_input=True)

    store_secret("GROWW_API_KEY", api_key)
    store_secret("GROWW_API_SECRET", api_secret)

    if click.confirm("Also store an access token? (optional)", default=False):
        token = click.prompt("GROWW_ACCESS_TOKEN", hide_input=True)
        store_secret("GROWW_ACCESS_TOKEN", token)

    click.echo("\nCredentials saved to Keychain.")
    click.echo("Remove them from .env if you pasted them there:")
    click.echo("  grow-assistant secrets scrub-env")


@secrets_group.command("set-token")
@click.option("--file", "token_file", type=click.Path(exists=True), help="Read token from a text file")
@click.option("--visible", is_flag=True, help="Show characters while typing (use if paste fails)")
def secrets_set_token(token_file: str | None, visible: bool) -> None:
    """Store only the daily Groww access token (starts with eyJ...)."""
    import sys

    from grow_trade_assistant.secrets import backend_name, store_secret

    click.echo("Store today's Groww access token in Keychain.")
    click.echo(f"Backend: {backend_name()}")
    click.echo("Token expires daily (~6 AM IST). Re-run this each trading day.\n")

    token = ""
    if token_file:
        token = Path(token_file).read_text(encoding="utf-8").strip()
        click.echo(f"Read token from file: {token_file}")
    elif not sys.stdin.isatty():
        token = sys.stdin.read().strip()
        click.echo("Read token from stdin.")
    else:
        click.echo("Paste your token, then press Enter.")
        click.echo("(Hidden mode: nothing appears while pasting — that is normal.)\n")
        if not visible:
            click.echo("If paste does not work, retry with: grow-assistant secrets set-token --visible\n")
        token = click.prompt(
            "GROWW_ACCESS_TOKEN",
            hide_input=not visible,
        ).strip()

    if not token:
        click.echo(
            "Error: empty token. Paste failed or nothing was entered.\n"
            "Try one of these:\n"
            "  grow-assistant secrets set-token --visible\n"
            "  grow-assistant secrets set-token --file ~/token.txt",
            err=True,
        )
        raise SystemExit(1)

    if not looks_like_access_token(token):
        click.echo(
            "Warning: access tokens usually start with eyJ... "
            "Make sure you pasted the access token, not the API key.",
            err=True,
        )
        if not click.confirm("Save this value anyway?", default=False):
            raise click.Abort()

    store_secret("GROWW_ACCESS_TOKEN", token)
    from grow_trade_assistant.secrets import mask_value

    click.echo(f"\nAccess token saved ({mask_value(token)}).")
    click.echo("Run: grow-assistant verify-auth")


@secrets_group.command("status")
def secrets_status() -> None:
    """Show which credentials are stored (values masked)."""
    from grow_trade_assistant.secrets import (
        backend_name,
        get_secret,
        list_stored_secrets,
        mask_value,
    )

    click.echo(f"Keychain backend: {backend_name()}\n")
    stored = list_stored_secrets()
    for env_name, is_stored in stored.items():
        if is_stored:
            val = get_secret(env_name) or ""
            click.echo(f"  {env_name}: {mask_value(val)} (Keychain)")
        else:
            click.echo(f"  {env_name}: not stored")


@secrets_group.command("delete")
@click.confirmation_option(prompt="Delete all Groww credentials from Keychain?")
def secrets_delete() -> None:
    """Remove all credentials from Keychain."""
    from grow_trade_assistant.secrets import delete_all_secrets

    count = delete_all_secrets()
    click.echo(f"Removed {count} credential(s) from Keychain.")


@secrets_group.command("migrate")
@click.option("--scrub-env/--no-scrub-env", default=True, help="Remove secrets from .env after migrate")
def secrets_migrate(scrub_env: bool) -> None:
    """Move credentials from .env into Keychain, then optionally scrub .env."""
    from dotenv import dotenv_values

    from grow_trade_assistant.secrets import SECRET_FIELDS, store_secret

    env_path = Path(".env")
    if not env_path.exists():
        click.echo("No .env file found.", err=True)
        sys.exit(1)

    values = dotenv_values(env_path)
    migrated = 0
    for env_name in SECRET_FIELDS:
        val = (values.get(env_name) or "").strip()
        if val and val not in ("your_api_key_here", "your_api_secret_here"):
            store_secret(env_name, val)
            migrated += 1
            click.echo(f"  Migrated {env_name} → Keychain")

    if migrated == 0:
        click.echo("No credentials found in .env to migrate.")
        click.echo(
            "\nYour .env likely has template placeholders, or you copied .env.example over it.\n"
            "Store credentials in Keychain instead:\n"
            "  grow-assistant secrets set"
        )
        sys.exit(1)

    click.echo(f"\nMigrated {migrated} credential(s) to Keychain.")

    if scrub_env:
        _scrub_env_secrets(env_path)
        click.echo("Removed secret values from .env (non-secret settings kept).")


@secrets_group.command("scrub-env")
def secrets_scrub_env() -> None:
    """Remove credential lines from .env (keep non-secret settings)."""
    env_path = Path(".env")
    if not env_path.exists():
        click.echo("No .env file found.", err=True)
        sys.exit(1)
    _scrub_env_secrets(env_path)
    click.echo("Secret values removed from .env.")


def _scrub_env_secrets(env_path: Path) -> None:
    from grow_trade_assistant.secrets import SECRET_FIELDS

    lines = env_path.read_text(encoding="utf-8").splitlines()
    secret_names = set(SECRET_FIELDS.keys())
    out: list[str] = []
    for line in lines:
        key = line.split("=", 1)[0].strip() if "=" in line else ""
        if key in secret_names:
            out.append(f"# {key}=  (stored in macOS Keychain — run: grow-assistant secrets set)")
        else:
            out.append(line)
    env_path.write_text("\n".join(out) + "\n", encoding="utf-8")


@main.command("my-ip")
def my_ip() -> None:
    """Show your public IP to whitelist on Groww Cloud API Keys page."""
    import httpx

    try:
        response = httpx.get("https://api.ipify.org", timeout=10.0)
        response.raise_for_status()
        ip = response.text.strip()
    except httpx.HTTPError as exc:
        click.echo(f"Could not detect public IP: {exc}", err=True)
        sys.exit(1)

    click.echo(f"Your public IP: {ip}")
    click.echo("\nAdd this IP on Groww Cloud API Keys page (IP whitelist).")
    click.echo("Note: home WiFi IPs can change. Re-run this command if auth fails later.")


@main.group("mf")
def mf_group() -> None:
    """Manage mutual fund holdings (Groww API does not expose MF — add manually)."""


@mf_group.command("search")
@click.argument("query")
def mf_search(query: str) -> None:
    """Search mutual fund by name to find scheme_code."""
    results = search_schemes(query)
    if not results:
        click.echo(f"No funds found for '{query}'")
        return
    click.echo(f"\nFound {len(results)} fund(s):\n")
    for r in results:
        click.echo(f"  {r['scheme_code']}  {r['name']}")
    click.echo("\nAdd with: grow-assistant mf add")


def _mf_config_path() -> Path:
    from dotenv import load_dotenv
    import os

    load_dotenv(override=False)
    return Path(os.getenv("MUTUAL_FUNDS_PATH", "./mutual_funds.json").strip() or "./mutual_funds.json")


@mf_group.command("list")
def mf_list() -> None:
    """Show mutual funds in your config file."""
    path = _mf_config_path()
    holdings = load_mutual_fund_file(path)
    if not holdings:
        click.echo("No mutual funds configured.")
        click.echo("\nGroww Trading API stocks hi dikhata hai — MF alag se add karna padta hai.")
        click.echo('Search: grow-assistant mf search "Parag Parikh"')
        click.echo("Add:    grow-assistant mf add")
        return
    click.echo(f"File: {path}\n")
    for h in holdings:
        click.echo(
            f"  {h.get('scheme_code')}  {h.get('name')}  units={h.get('units')} avg_nav={h.get('avg_nav')}"
        )


@mf_group.command("add")
@click.argument("query", required=False)
@click.option("--scheme-code", help="AMFI scheme code (skip search)")
@click.option("--units", type=float, default=None, help="Units you hold (from Groww app)")
@click.option("--avg-nav", type=float, default=None, help="Average buy NAV")
@click.option("--name", "fund_name", default=None, help="Fund display name")
@click.option("--category", default="", help="Optional category")
def mf_add(
    query: str | None,
    scheme_code: str | None,
    units: float | None,
    avg_nav: float | None,
    fund_name: str | None,
    category: str,
) -> None:
    """Add a mutual fund holding to mutual_funds.json.

    Examples:
      grow-assistant mf add
      grow-assistant mf add "Parag Parikh Flexi Cap" --units 12.5 --avg-nav 80
      grow-assistant mf add --scheme-code 122639 --units 12.5 --avg-nav 80
    """
    path = _mf_config_path()
    name = fund_name

    if scheme_code:
        name = name or (query or f"Scheme {scheme_code}")
    else:
        search_q = query or click.prompt("Fund name to search")
        results = search_schemes(search_q, limit=8)
        if not results:
            click.echo("No results. Enter scheme_code manually.")
            scheme_code = click.prompt("scheme_code")
            name = name or click.prompt("Fund name")
        elif len(results) == 1:
            scheme_code = results[0]["scheme_code"]
            name = name or results[0]["name"]
            click.echo(f"Matched: [{scheme_code}] {name}")
        else:
            click.echo("\nSelect fund:")
            for i, r in enumerate(results, 1):
                click.echo(f"  {i}. [{r['scheme_code']}] {r['name']}")
            choice = click.prompt("Number", type=int)
            if choice < 1 or choice > len(results):
                raise click.Abort()
            scheme_code = results[choice - 1]["scheme_code"]
            name = name or results[choice - 1]["name"]

    if units is None:
        units = click.prompt("Units (Groww app se)", type=float, default=0.0)
    if avg_nav is None:
        avg_nav = click.prompt("Average NAV (Groww app se)", type=float, default=0.0)

    holding = {
        "scheme_code": str(scheme_code),
        "name": name,
        "units": units,
        "avg_nav": avg_nav,
    }
    if category:
        holding["category"] = category

    add_holding(path, holding)
    click.echo(f"\nSaved to {path}")
    click.echo("Fill units/avg_nav from Groww if they are 0, then: grow-assistant analyze")


@main.command("import")
@click.argument("path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option(
    "--kind",
    type=click.Choice(["auto", "stocks", "mf"]),
    default="auto",
    help="Groww stocks holdings vs mutual fund report",
)
def import_groww(path: Path, kind: str) -> None:
    """Import Groww CSV / Excel / Numbers for stocks or mutual funds."""
    from grow_trade_assistant.groww_import import parse_groww_file, save_stocks_file
    from grow_trade_assistant.mf_config import save_mutual_fund_file

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    result = parse_groww_file(path, kind=kind)
    stocks_path = Path("./stocks.json")
    mf_path = _mf_config_path()

    if result.stocks:
        save_stocks_file(stocks_path, result.stocks)
        click.echo(f"Saved {len(result.stocks)} stock(s) → {stocks_path}")
        for h in result.stocks:
            click.echo(
                f"  {h['trading_symbol']:12} qty={h['quantity']:g}  avg={h['average_price']:.2f}  "
                f"invested={h['invested_value']:.2f}"
            )
    if result.mutual_funds:
        save_mutual_fund_file(mf_path, result.mutual_funds)
        click.echo(f"Saved {len(result.mutual_funds)} fund(s) → {mf_path}")
        for h in result.mutual_funds:
            click.echo(
                f"  {h.get('scheme_code', '?'):8} {h.get('name', '')[:48]}  "
                f"units={h['units']:g} avg_nav={h['avg_nav']:.4f}"
            )
    for w in result.warnings:
        click.echo(f"Warning: {w}", err=True)
    if not result.stocks and not result.mutual_funds:
        raise click.ClickException("Nothing imported.")
    click.echo("\nNext: grow-assistant analyze --offline")


@main.command("dashboard")
@click.option("--host", default="127.0.0.1", help="Host to bind")
@click.option("--port", default=8765, help="Port to bind")
@click.pass_context
def dashboard(ctx: click.Context, host: str, port: int) -> None:
    """Launch local web dashboard to view portfolio analysis."""
    import uvicorn

    env_file = ctx.obj.get("env_file")
    try:
        settings = load_settings(env_file, require_groww=False)
    except ValueError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)

    from grow_trade_assistant.web.app import create_app

    app = create_app(settings)
    click.echo(f"\n  Dashboard: http://{host}:{port}\n")
    click.echo("  Press Ctrl+C to stop.\n")
    uvicorn.run(app, host=host, port=port, log_level="warning")


@main.command("checksum")
@click.argument("timestamp", required=False)
@click.pass_context
def checksum_cmd(ctx: click.Context, timestamp: str | None) -> None:
    """Generate a checksum for manual token testing (requires GROWW_API_SECRET in .env)."""
    import time as _time

    env_file = ctx.obj.get("env_file")
    settings = load_settings(env_file)
    ts = timestamp or str(int(_time.time()))
    cs = generate_checksum(settings.groww_api_secret, ts)
    click.echo(json.dumps({"timestamp": ts, "checksum": cs}))


if __name__ == "__main__":
    main()
