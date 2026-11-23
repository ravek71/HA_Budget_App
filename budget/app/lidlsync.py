"""Background sync of Lidl Plus receipts into the local database.

Supports ANY NUMBER of Lidl Plus accounts (``lidl_accounts`` table). One
sync run:

  1. for each account: exchange the stored refresh token for an access
     token (the refresh token ROTATES — the new one is persisted back into
     the account row),
  2. walk the paged receipts list (newest first) — the backend's
     pagination style (``skip``/``take`` vs legacy ``pageNumber``) is
     auto-detected on every run by probing a second page both ways,
  3. fetch the detail (v3) of every receipt not yet stored locally,
  4. upsert it into the ``receipts`` table (tagged with the account id),
  5. optionally book each new receipt as an expense transaction
     (``lidl_auto_book`` setting; category from ``lidl_auto_category`` or
     auto-detected by the name „Lidl”).

A dead token on one account does not abort the run — the remaining
accounts are still synced and the error is reported in the status.

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

PAGE_TAKE = 25  # the server's page cap (take=50 still returns ~25)
DETAIL_PAUSE_S = 0.25  # be gentle with the unofficial API
MAX_PAGES = 200  # safety cap (200 x 50 = 10000 receipts)

LEGACY_TOKEN_SETTING = "lidl_refresh_token"  # 0.2.x: single token in settings


class LidlSync:
    def __init__(self, data: BudgetData, settings: Settings) -> None:
        self._data = data
        self._settings = settings
        self._lock = threading.Lock()
        self._tokens: dict[str, dict[str, Any]] = {}  # account_id -> cache
        self._status: dict[str, Any] = {
            "syncing": False,
            "phase": "",
            "last_sync": None,
            "last_new": None,
            "last_error": None,
            "accounts": [],
        }
        self._migrate_legacy_token()

    # ---------------------------------------------------------------- state

    def _migrate_legacy_token(self) -> None:
        """0.2.x stored one refresh token in settings/options — move it
        into the lidl_accounts table as the first account (once)."""
        if self._data.lidl_accounts():
            return
        legacy = (
            self._data.get_setting(LEGACY_TOKEN_SETTING)
            or self._settings.lidl_refresh_token
            or ""
        ).strip()
        if legacy:
            self._data.add_lidl_account("lidl", "Konto Lidl Plus", legacy)
            log.info("lidl: zaktualizowano 1 konto z opcji lidl_refresh_token")

    @property
    def configured(self) -> bool:
        """At least one account with a token exists."""
        return any(
            a["refresh_token"].strip() for a in self._data.lidl_accounts()
        )

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {**self._status, "configured": self.configured}

    def _set_status(self, **kwargs: Any) -> None:
        with self._lock:
            self._status.update(kwargs)

    # ------------------------------------------------------------ access tok

    def _access_token(self, account_id: str, force: bool = False) -> str:
        cache = self._tokens.get(account_id)
        if (
            not force
            and cache
            and time.time() < float(cache.get("expires_at", 0)) - 60
        ):
            return str(cache["access"])
        acct = self._data.lidl_account(account_id)
        refresh_token = (
            acct["refresh_token"] if acct else ""
        ).strip()
        if not refresh_token:
            raise lidl.LidlError(
                f"Konto {account_id}: brak tokena — dodaj je w zakładce "
                "„Lidl - paragony” (jak go zdobyć: tools/get_lidl_token.py)"
            )
        access, new_refresh, ttl = lidl.refresh(refresh_token)
        if new_refresh and new_refresh != refresh_token:
            # rotation: the old refresh token is now invalid
            self._data.set_lidl_account_token(account_id, new_refresh)
        self._tokens[account_id] = {
            "access": access,
            "expires_at": time.time() + int(ttl),
        }
        return str(access)

    def _with_retry(
        self, account_id: str, func, *args: Any, **kwargs: Any
    ) -> Any:
        """Call a lidl API function; re-auth once on 401, back off on 429."""
        for attempt in range(3):
            try:
                return func(self._access_token(account_id), *args, **kwargs)
            except lidl.LidlAuthError:
                if attempt == 0:
                    self._tokens.pop(account_id, None)
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
                syncing=True,
                phase="start",
                last_error=None,
                last_new=None,
                accounts=[
                    {"id": a["id"], "name": a["name"]}
                    for a in self._data.lidl_accounts()
                ],
            )
        threading.Thread(target=self._run, name="lidl-sync", daemon=True).start()
        return True

    def _run(self) -> None:
        errors: list[str] = []
        total_new = 0
        try:
            accounts = self._data.lidl_accounts()
            if not accounts:
                raise lidl.LidlError(
                    "Brak kont Lidl Plus — dodaj konto w zakładce „Lidl - paragony”"
                )
            for acct in accounts:
                label = acct["name"] or acct["id"]
                try:
                    new = self._sync_account(acct["id"], label)
                    total_new += new
                except lidl.LidlError as exc:
                    # one dead account must not abort the whole run
                    errors.append(f"{label}: {exc}")
                    log.warning("lidl sync: konto %s pominięte: %s", label, exc)
            stamp = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())
            self._set_status(
                syncing=False,
                phase="",
                last_sync=stamp,
                last_new=total_new,
                last_error="; ".join(errors) or None,
            )
            log.info(
                "lidl sync: zakończono %s (nowych %d, błędów %d)",
                stamp,
                total_new,
                len(errors),
            )
        except Exception as exc:  # noqa: BLE001 — report, don't kill the app
            log.exception("lidl sync failed")
            self._set_status(
                syncing=False,
                phase="",
                last_error=str(exc),
            )

    def _sync_account(self, account_id: str, label: str) -> int:
        """Sync one account fully (all pages); returns new receipts count."""
        country = self._settings.lidl_country
        language = self._settings.lidl_language
        self._set_status(phase=f"{label}: logowanie...")
        known = set(self._data.receipt_ids())  # stored locally (no refetch)
        seen_run: set[str] = set()  # ids seen during THIS run (stuck pages)
        new, errors, fetched, no_html = 0, 0, 0, 0
        total: int | None = None  # server-reported list length (if known)

        # page 1 — skip=0 and pageNumber=1 carry the same content
        self._set_status(phase=f"{label}: strona 1...")
        page, total = self._with_retry(
            account_id,
            lidl.list_tickets,
            country,
            language,
            skip=0,
            take=PAGE_TAKE,
        )
        # detect how THIS backend pages: the unofficial API has two
        # generations (skip/take vs legacy pageNumber) and silently
        # ignores the parameter it does not know — probe a second page
        # with both styles before walking the list
        mode = "skip"
        if page and (total is None or total > len(page)):
            probe, t = self._with_retry(
                account_id,
                lidl.list_tickets,
                country,
                language,
                skip=PAGE_TAKE,
                take=PAGE_TAKE,
            )
            if t is not None:
                total = t
            first = set(_page_id_list(page))
            probe_ids = set(_page_id_list(probe))
            if probe_ids - first:
                mode = "skip"  # skip advances the list
            elif probe_ids == first:
                # skip ignored (returned page 1 again) — try the legacy
                # pageNumber style
                legacy, t = self._with_retry(
                    account_id,
                    lidl.list_tickets,
                    country,
                    language,
                    page_number=2,
                )
                if t is not None:
                    total = t
                leg_ids = set(_page_id_list(legacy))
                if leg_ids and leg_ids == first:
                    mode = "none"  # both parameters ignored
                else:
                    # new ids (works) or empty (list shorter than a
                    # page) — "page" mode stops cleanly on the empty page
                    mode = "page"
            # else: probe empty -> list exhausted, skip works
        log.info(
            "lidl sync: %s: stronicowanie: %s (total=%s)",
            label, mode, total,
        )

        skip, page_no, last = 0, 1, page
        for page_no in range(1, MAX_PAGES + 1):
            page = last
            if not page:
                break
            self._set_status(
                phase=f"{label}: strona {page_no}"
                      + (f" (od {skip})" if mode == "skip" else "")
                      + f"... nowych: {new}"
            )
            page_ids = _page_id_list(page)
            # STUCK: the whole page repeats ids already seen in this run —
            # the backend does not advance with the probed parameter and
            # further pages would repeat forever, so stop. IMPORTANT: ids
            # already stored in the DB are NOT a stop condition — a
            # previous sync may have stored page 1 while pages 2..N are
            # still missing and must be fetched now.
            if page_ids and set(page_ids) <= seen_run:
                log.info(
                    "lidl sync: %s: strona %d powtórzona — koniec listy",
                    label, page_no,
                )
                break
            seen_run.update(page_ids)
            fetched += len(page_ids)
            for item in page:
                ticket_id = str(item.get("id") or "").strip()
                if not ticket_id or ticket_id in known:
                    continue
                try:
                    detail = self._with_retry(
                        account_id,
                        lidl.ticket_detail,
                        country,
                        language,
                        ticket_id,
                    )
                except lidl.LidlError as exc:
                    errors += 1
                    log.warning(
                        "lidl sync: paragon %s pominięty: %s", ticket_id, exc
                    )
                    continue
                # printed content: current backends use
                # htmlPrintedReceipt, older generations may carry it
                # under "html" — take the first non-empty
                html = str(
                    detail.get("htmlPrintedReceipt") or detail.get("html") or ""
                )
                if not html.strip():
                    # Lidl Plus keeps the digital receipt content only
                    # for recent tickets; older ones arrive without it.
                    # The metadata below is still stored and bookable.
                    no_html += 1
                    log.info(
                        "lidl sync: %s: paragon %s bez tresci html "
                        "(starszy bon?)", label, ticket_id,
                    )
                self._data.upsert_receipt(
                    receipt_id=ticket_id,
                    date_str=str(
                        detail.get("date") or item.get("date") or ""
                    ),
                    store=_store_label(detail.get("store")),
                    total=_to_float(
                        detail.get("totalAmount")
                        or item.get("totalAmount")
                        or 0
                    ),
                    articles=int(
                        detail.get("articlesCount")
                        or item.get("articlesCount")
                        or 0
                    ),
                    html=html,
                    raw=_to_json(detail),
                    datetime_str=str(
                        detail.get("date") or item.get("date") or ""
                    ),
                    account=account_id,
                )
                new += 1
                known.add(ticket_id)
                self.auto_book(account_id, ticket_id)
                self._set_status(
                    phase=f"{label}: pobieranie paragonów... nowych: {new}"
                )
                time.sleep(DETAIL_PAUSE_S)
            # advance to the next page in the detected style; the
            # server-reported total is the authoritative end when the
            # wrapper provides it
            if mode == "none" or (total is not None and fetched >= total):
                break
            if mode == "skip":
                skip += len(page)
                nxt, t = self._with_retry(
                    account_id,
                    lidl.list_tickets,
                    country,
                    language,
                    skip=skip,
                    take=PAGE_TAKE,
                )
            else:
                nxt, t = self._with_retry(
                    account_id,
                    lidl.list_tickets,
                    country,
                    language,
                    page_number=page_no + 1,
                )
            if t is not None:
                total = t
            last = nxt
        else:
            log.warning(
                "lidl sync: %s: osiągnięto limit %d stron — lista może "
                "nie zostać pobrana w całości", label, MAX_PAGES,
            )
        if mode == "none" and page and len(page) >= PAGE_TAKE:
            # page 1 was stored above; a FULL page while BOTH parameters
            # are ignored means the list is almost certainly longer —
            # surface the limitation in the panel (last_error) instead of
            # silently stopping. A short page IS the end of the list.
            raise lidl.LidlError(
                f"API nie przesuwa listy (skip i pageNumber ignorowane) — "
                f"pobrano tylko pierwszą stronę ({len(page)} paragonów); "
                f"starsze mogły nie zostać pobrane; diagnostyka: "
                f"tools/debug_lidl.py"
            )
        if errors:
            log.warning("lidl sync: konto %s: %d paragonów pominiętych", label, errors)
        if no_html:
            log.warning(
                "lidl sync: %s: %d paragonów bez treści html — Lidl Plus "
                "udostępnia treść cyfrową tylko dla nowszych bonów "
                "(metadane zapisano, panel pokaze dane podstawowe)",
                label, no_html,
            )
        return new

    # --------------------------------------------------------------- booking

    def auto_category_key(self) -> str:
        """Category to book Lidl receipts into: explicit setting wins,
        otherwise the first expense category whose name contains „lidl”."""
        key = (self._data.get_setting("lidl_auto_category") or "").strip()
        if key and self._data.get_category(key) is None:
            key = ""
        if not key:
            for c in self._data.categories():
                if c["kind"] == "expense" and "lidl" in c["name"].lower():
                    key = c["key"]
                    break
        return key

    @property
    def auto_book_enabled(self) -> bool:
        return self._data.get_setting("lidl_auto_book") != "0"

    def auto_book(self, account_id: str, receipt_id: str) -> None:
        """Create the expense transaction for one NEW receipt (idempotent)."""
        if not self.auto_book_enabled:
            return
        rec = self._data.receipt(receipt_id)
        if not rec or rec.get("booked_tx") or not (rec["total"] > 0):
            return
        key = self.auto_category_key()
        if not key:
            return
        try:
            tx_id = self._data.add_transaction(
                key,
                rec["total"],
                rec["date"][:10] or None,
                note=f"Paragon Lidl {receipt_id[:8]}",
            )
        except ValueError:
            return
        self._data.book_receipt(receipt_id, tx_id)
        log.info(
            "lidl auto-book: %s -> transakcja %d (%s)",
            receipt_id,
            tx_id,
            self._data.get_category(key)["name"],
        )


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


def _page_id_list(page: list[dict]) -> list[str]:
    """Cleaned ticket ids of one list page (order kept, dups dropped)."""
    seen: set[str] = set()
    out: list[str] = []
    for item in page:
        tid = str(item.get("id") or "").strip()
        if tid and tid not in seen:
            seen.add(tid)
            out.append(tid)
    return out
