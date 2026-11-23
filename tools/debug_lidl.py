r"""Diagnostyka API Lidl Plus — co dokładnie zwraca serwer?

Użycie (na PC, bez pakietów):

    python tools\debug_lidl.py              # poprosi o token (ukryty)
    python tools\debug_lidl.py <TOKEN>      # token jako argument

Wyświetla skrót KAŻDEGO wywołania (status, content-type, początek
ciała) dla: odświeżenia tokena, listy paragonów (v2 i v3) i detailu
pierwszego paragonu (v3). Nic nie zapisuje. Skopiuj CAŁY output i
prześlij — na tej podstawie poprawiamy klienta.
"""
from __future__ import annotations

import base64
import getpass
import json
import re
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request

COUNTRY = sys.argv[2].upper() if len(sys.argv) > 2 else "PL"
LANGUAGE = sys.argv[3].lower() if len(sys.argv) > 3 else "pl"
TOKEN = (
    sys.argv[1].strip()
    if len(sys.argv) > 1
    else getpass.getpass("Refresh token Lidl Plus (ukryty): ").strip()
)
if not TOKEN:
    print("Pusty token.", file=sys.stderr)
    sys.exit(1)

TOKEN_URL = "https://accounts.lidl.com/connect/token"


def request(method, url, data=None, headers=None):
    """(status, content-type, body) — HTTPError też zwraca status, nie rzuca."""

    def attempt(ctx):
        req = urllib.request.Request(
            url, data=data, headers=headers or {}, method=method
        )
        try:
            if ctx is not None:
                opener = urllib.request.build_opener(
                    urllib.request.HTTPSHandler(context=ctx)
                )
                with opener.open(req, timeout=45) as r:
                    return r.status, r.headers.get("Content-Type", ""), r.read()
            with urllib.request.urlopen(req, timeout=45) as r:
                return r.status, r.headers.get("Content-Type", ""), r.read()
        except urllib.error.HTTPError as e:
            with e:
                return e.code, e.headers.get("Content-Type", ""), e.read()

    try:
        return attempt(None)
    except urllib.error.URLError as exc:
        reason = str(getattr(exc, "reason", exc))
        if "certificate" not in reason.lower():
            raise
        print("(UWAGA: sieć inspekcjonuje TLS — ponawiam bez weryfikacji certyfikatu)")
        return attempt(ssl._create_unverified_context())


def preview(body: bytes) -> str:
    text = body.decode("utf-8", "replace")
    return text[:600]


def main() -> None:
    print(f"== Kraj: {COUNTRY}, język: {LANGUAGE}")

    # [1] odświeżenie tokena
    data = urllib.parse.urlencode(
        {"grant_type": "refresh_token", "refresh_token": TOKEN}
    ).encode("ascii")
    st, ct, body = request(
        "POST",
        TOKEN_URL,
        data,
        {
            "Authorization": "Basic "
            + base64.b64encode(b"LidlPlusNativeClient:secret").decode("ascii"),
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        },
    )
    print(f"[1] POST {TOKEN_URL} -> HTTP {st} ({ct})")
    try:
        j = json.loads(body) if body else {}
    except ValueError:
        j = {}
    print(f"    access_token: {'TAK' if j.get('access_token') else 'BRAK'}")
    print(f"    refresh_token: {'TAK' if j.get('refresh_token') else 'BRAK'}")
    if not j.get("access_token"):
        print("    body:", preview(body))
        print("KONIEC — bez access tokena dalej nie pójdziemy.")
        sys.exit(1)
    access = j["access_token"]

    headers = {
        "Authorization": f"Bearer {access}",
        "Accept": "application/json",
        "App-Version": "17.9.3",
        "Operating-System": "Android",
        "App": "com.lidl.eci.lidlplus",
        "Accept-Language": LANGUAGE,
    }

    def show(tag: str, url: str):
        st, ct, body = request("GET", url, None, headers)
        print(f"[{tag}] GET {url} -> HTTP {st} ({ct})")
        print("    body:", preview(body))
        return st, body

    print()
    st2, b2 = show("2", f"https://tickets.lidlplus.com/api/v2/{COUNTRY}/tickets?skip=0&take=3")
    print()
    st3, b3 = show("3", f"https://tickets.lidlplus.com/api/v3/{COUNTRY}/tickets?skip=0&take=3")
    print()

    m = re.search(rb'"id"\s*:\s*"([^"]+)"', b2) or re.search(
        rb'"id"\s*:\s*"([^"]+)"', b3
    )
    if m:
        tid = m.group(1).decode("utf-8", "replace")
        show("4", f"https://tickets.lidlplus.com/api/v3/{COUNTRY}/tickets/{tid}")
    else:
        print("[4] — brak id paragonu do testu detailu")

    # [5][6][7] sonda paginacji (0.3.3): co zwraca API i jak stronicuje?
    # [5] skip=0, [6] skip=25 (czy skip przesuuje liste?),
    # [7] pageNumber=2 (stary parametr API — czy jeszcze zyw?)
    def describe(body: bytes) -> tuple[list[str], str]:
        """(lista id paragonow, opis formatu odpowiedzi)."""
        try:
            j = json.loads(body)
        except ValueError:
            return [], "brak JSON"
        if isinstance(j, dict):
            meta = {k: v for k, v in j.items() if not isinstance(v, list)}
            shape = "wrapper " + json.dumps(meta, ensure_ascii=False)
            for key in ("tickets", "items", "data", "result", "content"):
                if isinstance(j.get(key), list):
                    j = j[key]
                    break
            else:
                return [], shape
        elif isinstance(j, list):
            shape = "tablica (bez wrappera)"
        else:
            return [], "nieznany format"
        ids = [
            str(t.get("id"))
            for t in j
            if isinstance(t, dict) and t.get("id")
        ]
        return ids, shape

    print()
    st5, b5 = show("5", f"https://tickets.lidlplus.com/api/v2/{COUNTRY}/tickets?skip=0&take=25")
    ids5, shape5 = describe(b5)
    print(f"    -> format: {shape5}")
    print(f"    -> pozycji: {len(ids5)}, pierwsze id: {ids5[:3]}")
    print()
    st6, b6 = show("6", f"https://tickets.lidlplus.com/api/v2/{COUNTRY}/tickets?skip=25&take=25")
    ids6, shape6 = describe(b6)
    print(f"    -> format: {shape6}")
    print(f"    -> pozycji: {len(ids6)}, pierwsze id: {ids6[:3]}")
    print()
    st7, b7 = show("7", f"https://tickets.lidlplus.com/api/v2/{COUNTRY}/tickets?pageNumber=2&take=25")
    ids7, shape7 = describe(b7)
    print(f"    -> format: {shape7}")
    print(f"    -> pozycji: {len(ids7)}, pierwsze id: {ids7[:3]}")

    print()
    if not ids5:
        print("WNIOSK [5]: strona 1 pusta — lista nie zwraca nic (patrz [2]/[3]).")
    else:
        if ids6 and ids6[:3] == ids5[:3]:
            print("WNIOSK [6]: API IGNORUJE 'skip' — strona 2 == strona 1.")
        elif not ids6:
            print("WNIOSK [6]: lista ma mniej niż 25 pozycji (koniec normalny).")
        else:
            print("WNIOSK [6]: 'skip' DZIAŁA — strona 2 to inne pozycje.")
        if ids7 and ids7[:3] != ids5[:3]:
            print("WNIOSK [7]: 'pageNumber' też przesuwa listę (stary parametr żywy).")
        elif ids7 and ids7[:3] == ids5[:3]:
            print("WNIOSK [7]: 'pageNumber' ignorowany (znów strona 1).")
        else:
            print("WNIOSK [7]: 'pageNumber' nie zwrócił listy.")

    print()
    print("== KONIEC. Skopiuj CAŁY ten output i prześlij.")


if __name__ == "__main__":
    main()
