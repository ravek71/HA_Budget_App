"""Background sync of Lidl Plus receipts into the local database.

One sync run:
  1. exchange the stored refresh token for an access token (the refresh
     token ROTATES — the new one is persisted into the settings table),
  2. walk the paged receipts list (newest first),
  3. fetch the detail (v3) of every receipt not yet stored locally,
  4. upsert it into the ``receipts`` table.

The run happens in a daemon thread so the HTTP request returns
immediately; progress/errors are exposed through :meth:`LidlSync.status`.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from typing import Any

from . import lidl
from .config import Settings
from .data import BudgetData

log = logging.getLogger(__name__)

PAGE_TAKE = 50
DETAIL_PAUSE_S = 0.25  # be gentle with the unofficial API


class LidlSync:
    def __init__(self, data: BudgetData, settings: Settings) -> None:
        self._data = data
        self._settings = settings
        self._lock = threading.Lock()
        self._token: dict[str, Any] = {}
        self._status: dict[str, Any] = {
            "syncing": False,
            "phase": "",
            "last_sync": None,
            "last_new": None,
            "last_error": None,
        }

    # ---------------------------------------------------------------- state

    @property
    def configured(self) -> bool:
        """A token is available (stored from a previous sync, or option)."""
        return bool(
            self._data.get_setting("lidl_refresh_token")
            or self._settings.lidl_refresh_token
        )

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {**self._status, "configured": self.configured}

    def _set_status(self, **kwargs: Any) -> None:
        with self._lock:
            self._status.update(kwargs)

    # ------------------------------------------------------------ access tok

    def _access_token(self, force: bool = False) -> str:
        cached = self._token.get("access")
        if (
            not force
            and cached
            and time.time() < float(self._token.get("expires_at", 0)) - 60
        ):
            return cached
        refresh_token = (
            self._data.get_setting("lidl_refresh_token")
            or self._settings.lidl_refresh_token
            or ""
        ).strip()
        if not refresh_token:
            raise lidl.LidlError(
                "Brak tokena Lidl Plus — ustaw opcję lidl_refresh_token "
                "(jak go zdobyć: tools/get_lidl_token.py w repo, patrz README)."
            )
        access, new_refresh, ttl = lidl.refresh(refresh_token)
        if new_refresh and new_refresh != refresh_token:
            # rotation: the old refresh token is now invalid
            self._data.set_setting("lidl_refresh_token", new_refresh)
        self._token = {"access": access, "expires_at": time.time() + int(ttl)}
        return access

    def _with_retry(
        self, func, *args: Any, auth_retry: bool = True, **kwargs: Any
    ) -> Any:
        """Call a lidl API function; re-auth once on 401, back off on 429."""
        for attempt in range(3):
            try:
                return func(self._access_token(), *args, **kwargs)
            except lidl.LidlAuthError:
                if auth_retry and attempt == 0:
                    self._token = {}
                    continue
                raise
            except lidl.LidlError as exc:
                if "429" in str(exc) and attempt < 2:
                    time.sleep(3.0 * (attempt + 1))
                    continue
                raise
        raise lidl.LidlError("Lidl: zbyt wiele prób — spróbuj później")  # pragma: no cover

    # ----------------------------------------------------------------- sync

    def start(self) -> bool:
        """Start a sync run in the background; False if one is running."""
        with self._lock:
            if self._status["syncing"]:
                return False
            self._status.update(
                syncing=True, phase="start", last_error=None, last_new=None
            )
        threading.Thread(target=self._run, name="lidl-sync", daemon=True).start()
        return True

    def _run(self) -> None:
        try:
            self._set_status(phase="logowanie do Lidl Plus...")
            self._access_token()
            self._set_status(phase="pobieranie listy paragonów...")
            known = self._data.receipt_ids()
            skip, new, errors = 0, 0, 0
            while True:
                page = self._with_retry(
                    lidl.list_tickets,
                    self._settings.lidl_country,
                    self._settings.lidl_language,
                    skip=skip,
                    take=PAGE_TAKE,
                )
                for item in page:
                    ticket_id = str(item.get("id") or "").strip()
                    if not ticket_id or ticket_id in known:
                        continue
                    try:
                        detail = self._with_retry(
                            lidl.ticket_detail,
                            self._settings.lidl_country,
                            self._settings.lidl_language,
                            ticket_id,
                        )
                    except lidl.LidlError as exc:
                        errors += 1
                        log.warning("lidl sync: paragon %s pominięty: %s", ticket_id, exc)
                        continue
                    self._data.upsert_receipt(
                        receipt_id=ticket_id,
                        date_str=str(detail.get("date") or item.get("date") or ""),
                        store=_store_label(detail.get("store")),
                        total=_to_float(detail.get("totalAmount")),
                        articles=int(
                            detail.get("articlesCount")
                            or item.get("articlesCount")
                            or 0
                        ),
                        html=str(detail.get("htmlPrintedReceipt") or ""),
                        raw=_to_json(detail),
                        datetime_str=str(detail.get("date") or item.get("date") or ""),
                    )
                    known.add(ticket_id)
                    new += 1
                    self._set_status(phase=f"pobieranie paragonów... nowych: {new}")
                    time.sleep(DETAIL_PAUSE_S)
                if len(page) < PAGE_TAKE:
                    break
                skip += PAGE_TAKE
            stamp = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())
            self._set_status(
                syncing=False, phase="", last_sync=stamp, last_new=new
            )
            log.info(
                "lidl sync: zakończono %s (nowych %d, błędów %d)", stamp, new, errors
            )
        except Exception as exc:  # noqa: BLE001 — report, don't kill the app
            log.exception("lidl sync failed")
            self._set_status(syncing=False, phase="", last_error=str(exc))


def _to_float(value: Any) -> float:
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return 0.0


def _store_label(store: Any) -> str:
    if not isinstance(store, dict):
        return ""
    parts = [
        str(store.get("name") or "").strip(),
        str(store.get("locality") or "").strip(),
    ]
    return ", ".join(p for p in parts if p)


def _to_json(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError):
        return ""
