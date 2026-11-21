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
settings:      key/value (total_budget, lidl_auto_book, lidl_auto_category;
                legacy lidl_refresh_token is migrated into lidl_accounts)
receipts:      Lidl Plus receipts synced from the unofficial API — id
                (ticket id), account (lidl_accounts id), date, store, total,
                articles, html (htmlPrintedReceipt), raw (full detail JSON),
                booked_tx (transaction created from this receipt, if any),
                synced_at
lidl_accounts: Lidl Plus accounts (id, name, refresh token) — one or more
"""

from __future__ import annotations

import logging
import re
import sqlite3
import threading
from datetime import date, datetime
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
                CREATE TABLE IF NOT EXISTS receipts (
                    id TEXT PRIMARY KEY,
                    account TEXT NOT NULL DEFAULT 'lidl',
                    date TEXT NOT NULL,
                    datetime TEXT NOT NULL DEFAULT '',
                    store TEXT NOT NULL DEFAULT '',
                    total REAL NOT NULL DEFAULT 0,
                    articles INTEGER NOT NULL DEFAULT 0,
                    html TEXT NOT NULL DEFAULT '',
                    raw TEXT NOT NULL DEFAULT '',
                    booked_tx INTEGER,
                    booked_at TEXT NOT NULL DEFAULT '',
                    synced_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_receipts_date
                    ON receipts(date);
                CREATE TABLE IF NOT EXISTS lidl_accounts (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    refresh_token TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )
            self._conn.commit()
            # migrate receipts tables created by older versions (0.2.x)
            cols = {
                r["name"]
                for r in self._conn.execute("PRAGMA table_info(receipts)")
            }
            if "account" not in cols:
                self._conn.execute(
                    "ALTER TABLE receipts ADD COLUMN account TEXT NOT NULL"
                    " DEFAULT 'lidl'"
                )
            if "booked_tx" not in cols:
                self._conn.execute(
                    "ALTER TABLE receipts ADD COLUMN booked_tx INTEGER"
                )
            if "booked_at" not in cols:
                self._conn.execute(
                    "ALTER TABLE receipts ADD COLUMN booked_at TEXT NOT NULL"
                    " DEFAULT ''"
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

    def update_transaction(
        self,
        tx_id: int,
        category_key: str,
        amount: float,
        date_str: str,
        note: str,
    ) -> dict[str, Any]:
        """Update all editable fields of one transaction (id kept)."""
        if self.get_category(category_key) is None:
            raise ValueError(f"Brak kategorii: {category_key!r}")
        amount = round(float(amount), 2)
        if amount <= 0:
            raise ValueError("Kwota musi być większa od zera")
        d = (date_str or "").strip()
        if not d:
            raise ValueError("Podaj datę (YYYY-MM-DD)")
        date.fromisoformat(d)  # validates YYYY-MM-DD
        with self._lock:
            if self._conn is None:
                self.open()
            cur = self._conn.execute(
                "UPDATE transactions"
                " SET date = ?, category_key = ?, amount = ?, note = ?"
                " WHERE id = ?",
                (d, category_key, amount, (note or "").strip(), int(tx_id)),
            )
            self._conn.commit()
            if cur.rowcount == 0:
                raise ValueError(f"Brak transakcji o id {tx_id}")
        rows = self._query("SELECT * FROM transactions WHERE id = ?", (int(tx_id),))
        return dict(rows[0]) if rows else {}

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

    # -------------------------------------------------------------- receipts

    def upsert_receipt(
        self,
        receipt_id: str,
        date_str: str,
        store: str,
        total: float,
        articles: int,
        html: str,
        raw: str,
        datetime_str: str = "",
        account: str = "lidl",
    ) -> None:
        """Insert or replace one synced receipt (by ticket id).

        Booking fields (booked_tx/booked_at) survive a re-sync: replacing
        the receipt keeps the link to the budget transaction.
        """
        self._execute(
            "INSERT INTO receipts (id, account, date, datetime, store, total,"
            " articles, html, raw, synced_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
            " ON CONFLICT(id) DO UPDATE SET"
            " account = excluded.account, date = excluded.date,"
            " datetime = excluded.datetime, store = excluded.store,"
            " total = excluded.total, articles = excluded.articles,"
            " html = excluded.html, raw = excluded.raw,"
            " synced_at = excluded.synced_at",
            (
                str(receipt_id),
                str(account or "lidl"),
                (date_str or "")[:10] or datetime.now().strftime("%Y-%m-%d"),
                datetime_str or "",
                (store or "").strip(),
                round(float(total or 0), 2),
                int(articles or 0),
                html or "",
                raw or "",
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            ),
        )

    def receipts(self) -> list[dict[str, Any]]:
        """List rows without the heavy html/raw columns (panel table)."""
        rows = self._query(
            "SELECT id, account, date, store, total, articles, booked_tx,"
            " synced_at FROM receipts ORDER BY datetime DESC, id DESC"
        )
        return [dict(r) for r in rows]

    def book_receipt(self, receipt_id: str, tx_id: int) -> None:
        """Link a synced receipt to the transaction created from it."""
        self._execute(
            "UPDATE receipts SET booked_tx = ?, booked_at = ? WHERE id = ?",
            (
                int(tx_id),
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                str(receipt_id),
            ),
        )

    def unbook_receipt(self, receipt_id: str) -> None:
        """Clear the booking link (the transaction is deleted by the caller)."""
        self._execute(
            "UPDATE receipts SET booked_tx = NULL, booked_at = '' WHERE id = ?",
            (str(receipt_id),),
        )

    def receipt(self, receipt_id: str) -> Optional[dict[str, Any]]:
        rows = self._query(
            "SELECT * FROM receipts WHERE id = ?", (str(receipt_id),)
        )
        return dict(rows[0]) if rows else None

    def receipt_ids(self) -> set[str]:
        rows = self._query("SELECT id FROM receipts")
        return {r["id"] for r in rows}

    def delete_receipt(self, receipt_id: str) -> bool:
        with self._lock:
            if self._conn is None:
                self.open()
            cur = self._conn.execute(
                "DELETE FROM receipts WHERE id = ?", (str(receipt_id),)
            )
            self._conn.commit()
            return cur.rowcount > 0

    # ----------------------------------------------------------- lidl accounts

    def lidl_accounts(self) -> list[dict[str, Any]]:
        rows = self._query(
            "SELECT id, name, refresh_token, created_at"
            " FROM lidl_accounts ORDER BY created_at, id"
        )
        return [dict(r) for r in rows]

    def lidl_account(self, account_id: str) -> Optional[dict[str, Any]]:
        rows = self._query(
            "SELECT * FROM lidl_accounts WHERE id = ?", (str(account_id),)
        )
        return dict(rows[0]) if rows else None

    def add_lidl_account(
        self, account_id: str, name: str, refresh_token: str
    ) -> dict[str, Any]:
        self._execute(
            "INSERT INTO lidl_accounts (id, name, refresh_token, created_at)"
            " VALUES (?, ?, ?, ?)",
            (
                str(account_id),
                (name or "Konto Lidl").strip(),
                (refresh_token or "").strip(),
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            ),
        )
        return self.lidl_account(account_id)  # type: ignore[return-value]

    def set_lidl_account_token(self, account_id: str, refresh_token: str) -> None:
        self._execute(
            "UPDATE lidl_accounts SET refresh_token = ? WHERE id = ?",
            ((refresh_token or "").strip(), str(account_id)),
        )

    def set_lidl_account_name(self, account_id: str, name: str) -> None:
        self._execute(
            "UPDATE lidl_accounts SET name = ? WHERE id = ?",
            ((name or "").strip(), str(account_id)),
        )

    def remove_lidl_account(self, account_id: str) -> bool:
        with self._lock:
            if self._conn is None:
                self.open()
            cur = self._conn.execute(
                "DELETE FROM lidl_accounts WHERE id = ?", (str(account_id),)
            )
            self._conn.commit()
            return cur.rowcount > 0

    # ------------------------------------------------------------- budgets

    def get_total_budget(self) -> float:
        rows = self._query(
            "SELECT value FROM settings WHERE key = 'total_budget'"
        )
        return float(rows[0]["value"]) if rows else 0.0

    def get_setting(self, key: str) -> Optional[str]:
        rows = self._query("SELECT value FROM settings WHERE key = ?", (key,))
        return rows[0]["value"] if rows else None

    def set_setting(self, key: str, value: str) -> None:
        self._execute(
            "INSERT INTO settings (key, value) VALUES (?, ?)"
            " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, str(value)),
        )

    def delete_setting(self, key: str) -> None:
        self._execute("DELETE FROM settings WHERE key = ?", (key,))

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
