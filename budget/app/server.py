"""Flask REST API for the budget app.

The ingress panel is a static page (panel.PAGE); all data comes from
the /api/* endpoints below.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Any, Optional

from flask import Flask, jsonify, request, Response

from . import __version__
from .config import settings
from .data import BudgetData
from .lidlsync import LidlSync
from .panel import PAGE

log = logging.getLogger(__name__)


def _err(message: str, code: int = 400):
    return jsonify({"error": message}), code


def _as_float(value: Any, default: Optional[float]) -> Optional[float]:
    """float(value) rounded to 2 decimals, or `default` when invalid."""
    if value is None or isinstance(value, bool):
        return default
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return None


def _month_from_args() -> tuple[int, int, Optional[tuple]]:
    """(year, month) from query args; missing parts = current month.

    Returns (year, month, None) or (0, 0, error_response).
    """
    year: Optional[int] = None
    month: Optional[int] = None
    try:
        if request.args.get("year"):
            year = int(request.args["year"])
        if request.args.get("month"):
            month = int(request.args["month"])
    except (TypeError, ValueError):
        return 0, 0, _err("year/month muszą być liczbami")
    if (year is None) != (month is None):
        return 0, 0, _err("podaj rok i miesiąc razem")
    if year is not None and (not 1 <= month <= 12 or not 2000 <= year <= 2100):
        return 0, 0, _err("nieprawidłowy rok lub miesiąc")
    now = date.today()
    return year or now.year, month or now.month, None


def _json_body() -> dict:
    body = request.get_json(silent=True)
    return body if isinstance(body, dict) else {}


def make_app(data: BudgetData, sync: Optional[LidlSync] = None) -> Flask:
    app = Flask(__name__)

    @app.after_request
    def _cors(resp):  # pragma: no cover - passthrough
        resp.headers.setdefault("Access-Control-Allow-Origin", "*")
        return resp

    # ----------------------------------------------------------------- pages

    @app.get("/")
    def index():
        return PAGE

    @app.get("/healthz")
    def healthz():
        return jsonify({"status": "ok", "version": __version__})

    # ---------------------------------------------------------------- status

    @app.get("/api/status")
    def api_status():
        now = date.today()
        return jsonify(
            {
                "version": __version__,
                "auto_recurring": settings.auto_recurring,
                "month": {"year": now.year, "month": now.month},
                "total_budget": data.get_total_budget(),
            }
        )

    # --------------------------------------------------------------- summary

    @app.get("/api/summary")
    def api_summary():
        year, month, err = _month_from_args()
        if err:
            return err
        summary = data.month_summary(year, month)
        categories = {c["key"]: c for c in data.categories()}
        total_budget = data.get_total_budget()
        by_category = []
        for key, amount in summary["by_category"].items():
            cat = categories.get(key, {"name": key, "kind": "expense",
                                       "monthly_budget": 0.0})
            by_category.append(
                {
                    "key": key,
                    "name": cat["name"],
                    "kind": cat["kind"],
                    "amount": amount,
                    "budget": cat.get("monthly_budget") or 0.0,
                }
            )
        return jsonify(
            {
                "year": year,
                "month": month,
                "income": summary["income"],
                "expenses": summary["expenses"],
                "balance": summary["balance"],
                "total_budget": total_budget,
                "remaining": round(total_budget - summary["expenses"], 2),
                "by_category": by_category,
                "transactions": data.transactions(year, month),
            }
        )

    @app.get("/api/history")
    def api_history():
        """Series of the last 12 months (for the chart)."""
        now = date.today()
        pairs: list[tuple[int, int]] = []
        y, m = now.year, now.month
        for _ in range(12):
            pairs.append((y, m))
            m -= 1
            if m == 0:
                m, y = 12, y - 1
        series = []
        for yy, mm in reversed(pairs):
            s = data.month_summary(yy, mm)
            series.append(
                {
                    "year": yy,
                    "month": mm,
                    "income": s["income"],
                    "expenses": s["expenses"],
                    "balance": s["balance"],
                }
            )
        return jsonify(
            {"months": series, "total_budget": data.get_total_budget()}
        )

    # ------------------------------------------------------------- categories

    @app.get("/api/categories")
    def api_categories():
        return jsonify({"categories": data.categories()})

    @app.post("/api/categories")
    def api_add_category():
        body = _json_body()
        name = str(body.get("name") or "").strip()
        kind = str(body.get("kind") or "expense")
        recurring = bool(body.get("recurring"))
        budget = _as_float(body.get("monthly_budget"), 0.0)
        if budget is None or budget < 0:
            return _err("monthly_budget musi być liczbą >= 0")
        try:
            cat = data.add_category(name, kind, recurring, budget)
        except ValueError as exc:
            return _err(str(exc))
        return jsonify({"category": cat}), 201

    @app.put("/api/categories/<key>")
    def api_update_category(key: str):
        body = _json_body()
        name = body.get("name")
        kind = body.get("kind")
        recurring = body.get("recurring")
        budget: Optional[float] = None
        if body.get("monthly_budget") is not None:
            budget = _as_float(body.get("monthly_budget"), None)
            if budget is None or budget < 0:
                return _err("monthly_budget musi być liczbą >= 0")
        try:
            cat = data.update_category(
                key,
                name=str(name).strip() if name is not None else None,
                kind=str(kind) if kind is not None else None,
                recurring=bool(recurring) if recurring is not None else None,
                monthly_budget=budget,
            )
        except ValueError as exc:
            return _err(str(exc))
        return jsonify({"category": cat})

    @app.delete("/api/categories/<key>")
    def api_remove_category(key: str):
        try:
            data.remove_category(key)
        except ValueError as exc:
            return _err(str(exc))
        return jsonify({"ok": True})

    # ----------------------------------------------------------- transactions

    @app.post("/api/transactions")
    def api_add_transaction():
        body = _json_body()
        key = str(body.get("category") or "").strip()
        amount = _as_float(body.get("amount"), None)
        if amount is None or amount <= 0:
            return _err("amount musi być liczbą większą od zera")
        date_str = str(body.get("date") or "").strip() or None
        if date_str is not None and len(date_str) != 10:
            return _err("date w formacie YYYY-MM-DD")
        note = str(body.get("note") or "").strip()
        try:
            tx_id = data.add_transaction(key, amount, date_str, note)
        except ValueError as exc:
            return _err(str(exc))
        return jsonify({"ok": True, "id": tx_id}), 201

    @app.put("/api/transactions/<int:tx_id>")
    def api_update_transaction(tx_id: int):
        body = _json_body()
        key = str(body.get("category") or "").strip()
        amount = _as_float(body.get("amount"), None)
        if amount is None or amount <= 0:
            return _err("amount musi być liczbą większą od zera")
        date_str = str(body.get("date") or "").strip()
        if len(date_str) != 10:
            return _err("date w formacie YYYY-MM-DD")
        note = str(body.get("note") or "").strip()
        try:
            tx = data.update_transaction(tx_id, key, amount, date_str, note)
        except ValueError as exc:
            return _err(str(exc))
        return jsonify({"ok": True, "transaction": tx})

    @app.delete("/api/transactions/<int:tx_id>")
    def api_delete_transaction(tx_id: int):
        if not data.delete_transaction(tx_id):
            return _err("brak transakcji o tym id", 404)
        return jsonify({"ok": True})

    # ---------------------------------------------------------------- receipts

    @app.get("/api/receipts")
    def api_receipts():
        meta = sync.status() if sync is not None else {
            "configured": False,
            "syncing": False,
            "phase": "",
            "last_sync": None,
            "last_new": None,
            "last_error": None,
        }
        meta["receipts"] = data.receipts()
        meta["count"] = len(meta["receipts"])
        return jsonify(meta)

    @app.post("/api/receipts/sync")
    def api_receipts_sync():
        if sync is None:
            return _err("synchronizacja Lidl Plus nie jest dostępna")
        if not sync.configured:
            return _err(
                "Ustaw lidl_refresh_token w opcjach add-onu "
                "(jak go zdobyć: plik tools/get_lidl_token.py w repo — patrz README)."
            )
        if not sync.start():
            return _err("synchronizacja już trwa — poczekaj na koniec", 409)
        return jsonify({"started": True})

    @app.get("/api/receipts/<ticket_id>/print")
    def api_receipt_print(ticket_id: str):
        rec = data.receipt(ticket_id)
        if rec is None:
            return _err("brak paragonu o tym id", 404)
        html = rec.get("html") or ""
        if not html.strip():
            return Response(
                "<html><body><p>Brak treści paragonu w bazie (pusty html).</p>"
                "</body></html>",
                mimetype="text/html",
            )
        if "<html" not in html.lower():
            # older receipts may come as a fragment — wrap for printing
            html = (
                "<!doctype html><html><head><meta charset='utf-8'>"
                "<style>body{font-family:monospace,'Courier New',monospace;"
                "max-width:420px;margin:16px auto;font-size:13px}"
                "@media print{body{margin:0}}</style></head><body>"
                + html
                + "</body></html>"
            )
        return Response(html, mimetype="text/html")

    @app.delete("/api/receipts/<ticket_id>")
    def api_receipt_delete(ticket_id: str):
        if not data.delete_receipt(ticket_id):
            return _err("brak paragonu o tym id", 404)
        return jsonify({"ok": True})

    # ---------------------------------------------------------------- settings

    @app.put("/api/total_budget")
    def api_set_total_budget():
        body = _json_body()
        value = _as_float(body.get("amount"), None)
        if value is None:
            return _err("amount musi być liczbą")
        try:
            value = data.set_total_budget(value)
        except ValueError as exc:
            return _err(str(exc))
        return jsonify({"total_budget": value})

    @app.post("/api/recurring")
    def api_run_recurring():
        """Book the recurring transactions for the current month, now."""
        if not settings.auto_recurring:
            return _err(
                "automatyczne księgowanie stałych jest wyłączone w opcjach add-onu"
            )
        added = data.apply_recurring(date.today())
        return jsonify({"added": added})

    return app
