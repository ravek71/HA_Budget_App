"""Minimal client for the unofficial Lidl Plus receipts API.

Only the standard library is used (urllib). The flow (reverse-engineered by
the community, verified against app 17.9.3):

* Identity server: ``accounts.lidl.com`` (OAuth2, PKCE). The add-on never
  performs the interactive browser login — it only exchanges the stored
  *refresh token* for a short-lived access token. The refresh token
  ROTATES: every exchange returns a new one, which must be persisted.
* Receipts microservice: ``tickets.lidlplus.com``.
  - list:   ``GET /api/v2/{COUNTRY}/tickets?skip=&take=`` (JSON array,
    newest first; fields: id, date, totalAmount, articlesCount, ...)
  - detail: ``GET /api/v3/{COUNTRY}/tickets/{id}`` (JSON; contains
    ``htmlPrintedReceipt`` — an HTML reproduction of the printed receipt)

Requests must imitate the Android app (App-Version / Operating-System /
App headers) and carry the language as an ``Accept-Language`` *header*
(query parameters are ignored by the server).
"""
from __future__ import annotations

import base64
import json
import urllib.error
import urllib.parse
import urllib.request

TOKEN_URL = "https://accounts.lidl.com/connect/token"
TICKETS_BASE = "https://tickets.lidlplus.com/api"
CLIENT_ID = "LidlPlusNativeClient"
CLIENT_SECRET = "secret"  # literal — baked into the public app
APP_VERSION = "17.9.3"


class LidlError(Exception):
    """User-friendly error (message may be shown in the panel)."""


class LidlAuthError(LidlError):
    """401 — the access/refresh token was rejected; re-auth and retry."""


def _basic() -> str:
    return "Basic " + base64.b64encode(
        f"{CLIENT_ID}:{CLIENT_SECRET}".encode("ascii")
    ).decode("ascii")


def _http(
    method: str,
    url: str,
    data: bytes | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 30.0,
) -> object:
    req = urllib.request.Request(
        url, data=data, headers=headers or {}, method=method
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            raise LidlAuthError("Lidl: token odrzucony (401)") from exc
        snippet = exc.read()[:200].decode("utf-8", "replace")
        path = url.split("?", 1)[0]
        raise LidlError(f"Lidl: HTTP {exc.code} przy {path} — {snippet}") from exc
    except urllib.error.URLError as exc:
        raise LidlError(f"Lidl: błąd sieci ({exc.reason})") from exc
    except TimeoutError as exc:
        raise LidlError("Lidl: przekroczono czas oczekiwania") from exc
    try:
        return json.loads(body)
    except ValueError:
        return body.decode("utf-8", "replace")


def refresh(refresh_token: str) -> tuple[str, str, int]:
    """Exchange a refresh token for (access_token, new_refresh_token, ttl).

    The new refresh token may differ (rotation) — persist it.
    """
    data = urllib.parse.urlencode(
        {"grant_type": "refresh_token", "refresh_token": refresh_token}
    ).encode("ascii")
    result = _http(
        "POST",
        TOKEN_URL,
        data=data,
        headers={
            "Authorization": _basic(),
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        },
    )
    if not isinstance(result, dict) or "access_token" not in result:
        raise LidlError(
            "Lidl: nieoczekiwana odpowiedź przy odświeżaniu tokena: "
            + str(result)[:200]
        )
    new_rt = str(result.get("refresh_token") or refresh_token)
    try:
        expires_in = int(result.get("expires_in") or 1200)
    except (TypeError, ValueError):
        expires_in = 1200
    return str(result["access_token"]), new_rt, expires_in


def _app_headers(access_token: str, language: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
        "App-Version": APP_VERSION,
        "Operating-System": "Android",
        "App": "com.lidl.eci.lidlplus",
        # MUST be a header (2-letter code); query params are ignored
        "Accept-Language": language,
    }


def list_tickets(
    access_token: str,
    country: str,
    language: str,
    skip: int = 0,
    take: int = 50,
) -> tuple[list[dict], int | None]:
    """Paged receipts list (newest first).

    Returns ``(items, total_count)``. The server answers either a plain
    JSON array or a wrapper object (``tickets``/``items``/... plus
    ``page``/``size``/``totalCount`` — varies by region/version); both
    are accepted. ``total_count`` is the server-reported list length
    when the wrapper carries ``totalCount``, else None.
    """
    url = f"{TICKETS_BASE}/v2/{country}/tickets?skip={skip}&take={take}"
    result = _http("GET", url, headers=_app_headers(access_token, language))
    items: list[dict]
    total: int | None = None
    if isinstance(result, dict):
        # some regions/versions wrap the list in an object — accept the
        # common wrapper keys, fail with a body preview otherwise
        items = None
        for key in ("tickets", "items", "data", "result", "content"):
            if isinstance(result.get(key), list):
                items = result[key]
                break
        if items is None:
            raise LidlError(
                "Lidl: nieoczekiwany format listy paragonów: "
                + json.dumps(result, ensure_ascii=False)[:300]
            )
        tc = result.get("totalCount")
        if isinstance(tc, bool):
            tc = None
        if isinstance(tc, int):
            total = tc
        elif isinstance(tc, str) and tc.strip().isdigit():
            total = int(tc.strip())
    elif isinstance(result, list):
        items = result
    else:
        raise LidlError(
            "Lidl: nieoczekiwany format listy paragonów: "
            + str(result)[:300]
        )
    return items, total


def ticket_detail(
    access_token: str, country: str, language: str, ticket_id: str
) -> dict:
    # v3 on purpose: v2/{country}/tickets/{id} is a dead route (immediate 400)
    url = f"{TICKETS_BASE}/v3/{country}/tickets/{urllib.parse.quote(ticket_id)}"
    result = _http("GET", url, headers=_app_headers(access_token, language))
    if not isinstance(result, dict):
        raise LidlError(f"Lidl: nieoczekiwany format paragonu {ticket_id}")
    return result
