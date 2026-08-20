from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class DataStore:
    """SQLite cache for portfolio snapshots, LTP, and daily candles."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path))
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> DataStore:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def _init_schema(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS portfolio_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                captured_at TEXT NOT NULL,
                holdings_json TEXT NOT NULL,
                positions_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS ltp_cache (
                exchange_symbol TEXT NOT NULL,
                segment TEXT NOT NULL,
                ltp REAL NOT NULL,
                fetched_at TEXT NOT NULL,
                PRIMARY KEY (exchange_symbol, segment)
            );

            CREATE TABLE IF NOT EXISTS daily_candles (
                exchange TEXT NOT NULL,
                trading_symbol TEXT NOT NULL,
                ts INTEGER NOT NULL,
                open REAL NOT NULL,
                high REAL NOT NULL,
                low REAL NOT NULL,
                close REAL NOT NULL,
                volume REAL NOT NULL,
                PRIMARY KEY (exchange, trading_symbol, ts)
            );

            CREATE TABLE IF NOT EXISTS recommendation_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                action TEXT NOT NULL,
                suggested_at TEXT NOT NULL
            );
            """
        )
        self._conn.commit()

    def save_snapshot(
        self,
        holdings: list[dict[str, Any]],
        positions: list[dict[str, Any]],
    ) -> int:
        now = datetime.now(timezone.utc).isoformat()
        cur = self._conn.execute(
            """
            INSERT INTO portfolio_snapshots (captured_at, holdings_json, positions_json)
            VALUES (?, ?, ?)
            """,
            (now, json.dumps(holdings), json.dumps(positions)),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def get_latest_snapshot(self) -> dict[str, Any] | None:
        row = self._conn.execute(
            """
            SELECT id, captured_at, holdings_json, positions_json
            FROM portfolio_snapshots
            ORDER BY id DESC LIMIT 1
            """
        ).fetchone()
        if not row:
            return None
        return {
            "id": row["id"],
            "captured_at": row["captured_at"],
            "holdings": json.loads(row["holdings_json"]),
            "positions": json.loads(row["positions_json"]),
        }

    def get_previous_snapshot(self) -> dict[str, Any] | None:
        row = self._conn.execute(
            """
            SELECT id, captured_at, holdings_json, positions_json
            FROM portfolio_snapshots
            ORDER BY id DESC LIMIT 1 OFFSET 1
            """
        ).fetchone()
        if not row:
            return None
        return {
            "id": row["id"],
            "captured_at": row["captured_at"],
            "holdings": json.loads(row["holdings_json"]),
            "positions": json.loads(row["positions_json"]),
        }

    def cache_ltp(
        self, segment: str, prices: dict[str, float], fetched_at: str | None = None
    ) -> None:
        ts = fetched_at or datetime.now(timezone.utc).isoformat()
        for symbol, ltp in prices.items():
            self._conn.execute(
                """
                INSERT INTO ltp_cache (exchange_symbol, segment, ltp, fetched_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(exchange_symbol, segment) DO UPDATE SET
                    ltp=excluded.ltp,
                    fetched_at=excluded.fetched_at
                """,
                (symbol, segment, ltp, ts),
            )
        self._conn.commit()

    def get_cached_ltp(self, segment: str) -> dict[str, float]:
        rows = self._conn.execute(
            "SELECT exchange_symbol, ltp FROM ltp_cache WHERE segment = ?",
            (segment,),
        ).fetchall()
        return {row["exchange_symbol"]: row["ltp"] for row in rows}

    def upsert_candles(
        self,
        exchange: str,
        trading_symbol: str,
        candles: list[list[Any]],
    ) -> None:
        import math
        for candle in candles:
            if len(candle) < 6:
                continue
            ts, o, h, l, c, v = candle[:6]
            vals = [o, h, l, c, v]
            if any(x is None or (isinstance(x, float) and math.isnan(x)) for x in vals):
                continue
            if ts is None or (isinstance(ts, float) and math.isnan(ts)):
                continue
            self._conn.execute(
                """
                INSERT INTO daily_candles
                    (exchange, trading_symbol, ts, open, high, low, close, volume)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(exchange, trading_symbol, ts) DO UPDATE SET
                    open=excluded.open,
                    high=excluded.high,
                    low=excluded.low,
                    close=excluded.close,
                    volume=excluded.volume
                """,
                (exchange, trading_symbol, int(ts), float(o), float(h), float(l), float(c), float(v)),
            )
        self._conn.commit()

    def get_candles(
        self, exchange: str, trading_symbol: str, limit: int = 300
    ) -> list[dict[str, float]]:
        rows = self._conn.execute(
            """
            SELECT ts, open, high, low, close, volume
            FROM daily_candles
            WHERE exchange = ? AND trading_symbol = ?
            ORDER BY ts DESC
            LIMIT ?
            """,
            (exchange, trading_symbol, limit),
        ).fetchall()
        return [
            {
                "ts": row["ts"],
                "open": row["open"],
                "high": row["high"],
                "low": row["low"],
                "close": row["close"],
                "volume": row["volume"],
            }
            for row in reversed(rows)
        ]

    def record_recommendation(self, symbol: str, action: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """
            INSERT INTO recommendation_history (symbol, action, suggested_at)
            VALUES (?, ?, ?)
            """,
            (symbol, action, now),
        )
        self._conn.commit()

    def last_recommendation(self, symbol: str, action: str) -> str | None:
        row = self._conn.execute(
            """
            SELECT suggested_at FROM recommendation_history
            WHERE symbol = ? AND action = ?
            ORDER BY id DESC LIMIT 1
            """,
            (symbol, action),
        ).fetchone()
        return row["suggested_at"] if row else None
