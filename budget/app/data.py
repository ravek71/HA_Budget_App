"""SQLite storage layer for the Budżet domowy integration.

All methods are synchronous and must be called from an executor
(``hass.async_add_executor_job``). A single lock serializes access;
the connection is opened with ``check_same_thread=False``.

Data model
----------
categories:    key (slug), name, kind ('income' | 'expense'),
               recurring (0/1), monthly_budget (planned budget for the
               category, 0 = no planned budget)
transactions:  date (YYYY-MM-DD), category_key, amount (> 0, direction
               comes from the category kind), note
settings:      key/value (currently: total_budget)
"""

from __future__ import annotations

import logging
import re
import sqlite3
import threading
from datetime import date
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger(__package__)


def _slugify(name: str) -> str:
    """Build a short unique-ish key from a human category name."""
    slug = re.sub(r"[^a-z0-9]+", "_", name.strip().lower()).strip("_")
    return slug or "kategoria"


class BudgetData:
    """Thread-safe access to the per-entry SQLite database."""

    def __init__(self, path: Path | str) -> None:
        # hass.config.path() returns str — normalize to Path
        self._path = Path(path)
        self._lock = threading.Lock()
        self._conn: Optional[sqlite3.Connection] = None
        self.open()

    # ------------------------------------------------------------------ conn

    def open(self) -> None:
        with self._lock:
            if self._conn is not None:
                return
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(self._path), check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS categories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    key TEXT NOT NULL UNIQUE,
                    name TEXT NOT NULL,
                    kind TEXT NOT NULL DEFAULT 'expense'
                        CHECK (kind IN ('income', 'expense')),
                    recurring INTEGER NOT NULL DEFAULT 0,
                    monthly_budget REAL NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS transactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT NOT NULL,
                    category_key TEXT NOT NULL,
                    amount REAL NOT NULL CHECK (amount > 0),
                    note TEXT NOT NULL DEFAULT ''
                );
                CREATE INDEX IF NOT EXISTS idx_tx_date
                    ON transactions(date);
                CREATE INDEX IF NOT EXISTS idx_tx_category
                    ON transactions(category_key);
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                """
            )
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None

    def _execute(self, sql: str, params: tuple = ()) -> int:
        """Execute a write statement; returns lastrowid."""
        with self._lock:
            if self._conn is None:
                self.open()
            cur = self._conn.execute(sql, params)
            self._conn.commit()
            return cur.lastrowid or 0

    def _query(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        with self._lock:
            if self._conn is None:
                self.open()
            return self._conn.execute(sql, params).fetchall()

    # ------------------------------------------------------------- categories

    def categories(self) -> list[dict[str, Any]]:
        rows = self._query("SELECT * FROM categories ORDER BY kind, name")
        return [dict(r) for r in rows]

    def _unique_key(self, name: str, exclude: Optional[str] = None) -> str:
        base = _slugify(name)
        candidate, n = base, 2
        existing = {r["key"] for r in self._query("SELECT key FROM categories")}
        if exclude:
            existing.discard(exclude)
        while candidate in existing:
            candidate = f"{base}_{n}"
            n += 1
        return candidate

    def add_category(
        self,
        name: str,
        kind: str = "expense",
        recurring: bool = False,
        monthly_budget: float = 0.0,
    ) -> dict[str, Any]:
        if kind not in ("income", "expense"):
            raise ValueError(f"Nieprawidłowy typ kategorii: {kind!r}")
        if not name or not name.strip():
            raise ValueError("Nazwa kategorii nie może być pusta")
        key = self._unique_key(name)
        self._execute(
            "INSERT INTO categories (key, name, kind, recurring, monthly_budget)"
            " VALUES (?, ?, ?, ?, ?)",
            (key, name.strip(), kind, int(bool(recurring)), round(float(monthly_budget), 2)),
        )
        return self.get_category(key)  # type: ignore[return-value]

    def get_category(self, key: str) -> Optional[dict[str, Any]]:
        rows = self._query("SELECT * FROM categories WHERE key = ?", (key,))
        return dict(rows[0]) if rows else None

    def update_category(
        self,
        key: str,
        name: Optional[str] = None,
        kind: Optional[str] = None,
        recurring: Optional[bool] = None,
        monthly_budget: Optional[float] = None,
    ) -> dict[str, Any]:
        current = self.get_category(key)
        if current is None:
            raise ValueError(f"Brak kategorii: {key!r}")
        new_name = (name or "").strip() or current["name"]
        new_key = key
        if (name or "").strip() and new_name != current["name"]:
            new_key = self._unique_key(new_name, exclude=key)
        new_kind = kind or current["kind"]
        if new_kind not in ("income", "expense"):
            raise ValueError(f"Nieprawidłowy typ kategorii: {new_kind!r}")
        new_recurring = (
            int(bool(recurring)) if recurring is not None else current["recurring"]
        )
        new_budget = (
            round(float(monthly_budget), 2)
            if monthly_budget is not None
            else current["monthly_budget"]
        )
        if new_key != key:
            self._execute(
                "UPDATE transactions SET category_key = ? WHERE category_key = ?",
                (new_key, key),
            )
        self._execute(
            "UPDATE categories SET key = ?, name = ?, kind = ?,"
            " recurring = ?, monthly_budget = ? WHERE key = ?",
            (new_key, new_name, new_kind, new_recurring, new_budget, key),
        )
        return self.get_category(new_key)  # type: ignore[return-value]

    def remove_category(self, key: str) -> None:
        if self.get_category(key) is None:
            raise ValueError(f"Brak kategorii: {key!r}")
        rows = self._query(
            "SELECT COUNT(*) AS n FROM transactions WHERE category_key = ?", (key,)
        )
        if rows[0]["n"] > 0:
            raise ValueError(
                f"Kategoria {key!r} ma {rows[0]['n']} transakcji —"
                " usuń je najpierw (delete_transaction)"
            )
        self._execute("DELETE FROM categories WHERE key = ?", (key,))

    # ----------------------------------------------------------- transactions

    def add_transaction(
        self,
        category_key: str,
        amount: float,
        date_str: Optional[str] = None,
        note: str = "",
    ) -> int:
        if self.get_category(category_key) is None:
            raise ValueError(f"Brak kategorii: {category_key!r}")
        amount = round(float(amount), 2)
        if amount <= 0:
            raise ValueError("Kwota musi być większa od zera")
        d = date_str or date.today().isoformat()
        date.fromisoformat(d)  # validates YYYY-MM-DD
        return self._execute(
            "INSERT INTO transactions (date, category_key, amount, note)"
            " VALUES (?, ?, ?, ?)",
            (d, category_key, amount, (note or "").strip()),
        )

    def delete_transaction(self, tx_id: int) -> bool:
        """Delete one transaction by id; returns True if a row was removed."""
        with self._lock:
            if self._conn is None:
                self.open()
            cur = self._conn.execute(
                "DELETE FROM transactions WHERE id = ?", (int(tx_id),)
            )
            self._conn.commit()
            return cur.rowcount > 0

    def transactions(
        self, year: Optional[int] = None, month: Optional[int] = None
    ) -> list[dict[str, Any]]:
        sql = "SELECT * FROM transactions"
        params: list[Any] = []
        if year is not None and month is not None:
            start, end = _month_range(year, month)
            sql += " WHERE date >= ? AND date < ?"
            params = [start, end]
        sql += " ORDER BY date DESC, id DESC"
        rows = self._query(sql, tuple(params))
        return [dict(r) for r in rows]

    # ------------------------------------------------------------- budgets

    def get_total_budget(self) -> float:
        rows = self._query(
            "SELECT value FROM settings WHERE key = 'total_budget'"
        )
        return float(rows[0]["value"]) if rows else 0.0

    def set_total_budget(self, value: float) -> float:
        value = round(float(value), 2)
        if value < 0:
            raise ValueError("Budżet miesięczny nie może być ujemny")
        self._execute(
            "INSERT INTO settings (key, value) VALUES ('total_budget', ?)"
            " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (str(value),),
        )
        return value

    # ----------------------------------------------------------------- summary

    def month_summary(self, year: int, month: int) -> dict[str, Any]:
        """Income/expenses totals and per-category amounts for one month."""
        start, end = _month_range(year, month)
        kinds = {
            r["key"]: r["kind"] for r in self._query("SELECT key, kind FROM categories")
        }
        income = expenses = 0.0
        by_category: dict[str, float] = {}
        for row in self._query(
            "SELECT category_key, amount FROM transactions"
            " WHERE date >= ? AND date < ?",
            (start, end),
        ):
            amt = row["amount"]
            by_category[row["category_key"]] = (
                by_category.get(row["category_key"], 0.0) + amt
            )
            if kinds.get(row["category_key"], "expense") == "income":
                income += amt
            else:
                expenses += amt
        return {
            "income": round(income, 2),
            "expenses": round(expenses, 2),
            "balance": round(income - expenses, 2),
            "by_category": {k: round(v, 2) for k, v in sorted(by_category.items())},
        }

    def prev_month_summary(self, year: int, month: int) -> dict[str, Any]:
        py, pm = (year - 1, 12) if month == 1 else (year, month - 1)
        return self.month_summary(py, pm)

    # --------------------------------------------------------------- recurring

    def apply_recurring(self, today: date) -> int:
        """Add day-1 transactions for recurring categories (idempotent).

        Covers both recurring expenses (rent, ...) and recurring income
        (salary, ...).
        """
        date_str = today.replace(day=1).isoformat()
        added = 0
        for cat in self._query(
            "SELECT key, kind, monthly_budget FROM categories"
            " WHERE recurring = 1 AND monthly_budget > 0"
        ):
            exists = self._query(
                "SELECT 1 AS x FROM transactions"
                " WHERE category_key = ? AND date = ?",
                (cat["key"], date_str),
            )
            if not exists:
                note = "Wpływ stały (auto)" if cat["kind"] == "income" else "Wydatek stały (auto)"
                self.add_transaction(
                    cat["key"], cat["monthly_budget"], date_str, note=note
                )
                added += 1
        if added:
            log.info("apply_recurring: dodano %d transakcji stałych dla %s", added, date_str)
        return added


def _month_range(year: int, month: int) -> tuple[str, str]:
    """Inclusive start / exclusive end date strings for a month."""
    start = date(year, month, 1)
    y, m = (year + 1, 1) if month == 12 else (year, month + 1)
    end = date(y, m, 1)
    return start.isoformat(), end.isoformat()
