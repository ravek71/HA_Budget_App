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

    print()
    print("== KONIEC. Skopiuj CAŁY ten output i prześlij.")


if __name__ == "__main__":
    main()
