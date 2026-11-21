r"""Jednorazowy pomocnik: zdobycie refresh tokena Lidl Plus.

Uruchamij lokalnie na swoim PC (Python 3.8+, BEZ żadnych pakietów do
instalacji):

    python tools\get_lidl_token.py          # Polska (domyślnie)
    python tools\get_lidl_token.py PL pl    # kraj ISO-2 + język

Co się dzieje:
  1. Otwiera się przeglądarka — zaloguj się do Lidl Plus normalnie
     (email/telefon + hasło; captcha/2FA jeśli Lidl poprosi).
  2. Po zalogowaniu przeglądarka spróbuje otworzyć adres
     com.lidlplus.app://callback?code=... i pokaże błąd
     („nie znaleziono aplikacji” / „nie można otworzyć”) — TO JEST
     PRAWIDŁOWE. Skopiuj pełny adres z paska adresu (zaczyna się od
     com.lidlplus.app://callback) i wklej go w konsoli.
  3. Skrypt wyśle kod do Lidl i wypisze refresh token.

Wklej token do opcji add-onu „Budżet domowy” → lidl_refresh_token.

Uwagi:
  * Refresh token ROTUJE się przy każdym odświeżeniu — add-on sam
    przechowuje nową wersję w swojej bazie po pierwszej synchronizacji.
  * Token daje dostęp do Twojego konta Lidl Plus — trzymaj go jak hasło.
  * To nieoficjalne API aplikacji Lidl Plus (reverse engineered); Lidl
    może je zmienić lub zablokować w każdej chwili.
"""
from __future__ import annotations

import base64
import hashlib
import json
import secrets
import sys
import urllib.parse
import urllib.request
import webbrowser

COUNTRY = sys.argv[1].upper() if len(sys.argv) > 1 else "PL"
LANGUAGE = sys.argv[2].lower() if len(sys.argv) > 2 else "pl"

CLIENT_ID = "LidlPlusNativeClient"
CLIENT_SECRET = "secret"  # literal — publiczna stała z aplikacji Lidl
REDIRECT_URI = "com.lidlplus.app://callback"
AUTHORIZE_URL = "https://accounts.lidl.com/connect/authorize"
TOKEN_URL = "https://accounts.lidl.com/connect/token"


def main() -> None:
    print(f"Kraj: {COUNTRY}, język: {LANGUAGE}\n")

    # PKCE (S256) — dokładnie jak robi to aplikacja mobilna
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(48)).rstrip(b"=").decode()
    challenge = (
        base64.urlsafe_b64encode(
            hashlib.sha256(verifier.encode("ascii")).digest()
        ).rstrip(b"=").decode()
    )
    state = secrets.token_urlsafe(16)
    nonce = secrets.token_urlsafe(16)

    params = {
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": "openid profile offline_access lpprofile lpapis",
        "state": state,
        "nonce": nonce,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "Country": COUNTRY,
        "language": f"{LANGUAGE}-{COUNTRY}",
        "force": "false",
        "track": "false",
    }
    url = AUTHORIZE_URL + "?" + urllib.parse.urlencode(params)

    print("Otwieram przeglądarkę — zaloguj się do Lidl Plus normalnie...")
    print("(captcha/2FA jeśli poproszą; po zalogowaniu zobaczysz błąd\n"
          "„nie można otworzyć com.lidlplus.app” — skopiuj ten adres)\n")
    webbrowser.open(url)

    raw = (
        input("Wklej adres z paska (com.lidlplus.app://callback?...) albo sam code: ")
        .strip()
        .strip('"')
    )
    if not raw:
        print("Pusto — nic nie wklejono.", file=sys.stderr)
        sys.exit(1)

    if "code=" in raw:
        # pełny URL callbacku (http(s)://... albo com.lidlplus.app://...)
        q = raw.split("?", 1)[1] if "?" in raw else ""
        code = dict(urllib.parse.parse_qsl(q)).get("code", "")
        if not code:
            print("W wklejonym adresie nie ma parametru code=...", file=sys.stderr)
            sys.exit(1)
    else:
        code = raw

    data = urllib.parse.urlencode(
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT_URI,
            "code_verifier": verifier,
        }
    ).encode("ascii")
    req = urllib.request.Request(
        TOKEN_URL,
        data=data,
        headers={
            "Authorization": "Basic "
            + base64.b64encode(
                f"{CLIENT_ID}:{CLIENT_SECRET}".encode("ascii")
            ).decode("ascii"),
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        },
    )
    print("Wymieniam kod na token...")
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = json.loads(resp.read())

    refresh_token = body.get("refresh_token")
    if not refresh_token:
        print("Błąd — brak refresh_token w odpowiedzi:", body, file=sys.stderr)
        sys.exit(1)

    print("\n" + "=" * 70)
    print("Gotowe. Refresh token (wklej do opcji add-onu lidl_refresh_token):")
    print("=" * 70)
    print(refresh_token)
    print("=" * 70)
    print("Access token wygasa za ~20 min, ale add-on sam go odświeża.")
    print("Nowa wersja refresh tokena jest przechowywana w bazie add-onu.")


if __name__ == "__main__":
    main()
