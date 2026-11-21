# Budżet domowy — app add-on do Home Assistant

Aplikacja do **planowania i śledzenia domowego budżetu**: wpływy, wydatki,
**wydatki (i wpływy) stałe** automatycznie księgowane 1. dnia miesiąca,
**kategorie z planowanymi budżetami**, **wykres 12 miesięcy** i **pełna
historia**. Dane zapisywane lokalnie (SQLite, wolumen `/data` add-onu —
przetrwają restarty i aktualizacje), panel dostępny bezpośrednio w HA przez
**ingress** (ikona portfel w sidebarze).

Bez zewnętrznych zależności — tylko standardowa biblioteka Pythona
(`sqlite3`) + Flask.

## Co daje

- **Pulpit** — wpływy / wydatki / bilans / pozostało z budżetu, wykres
  12 miesięcy, rozbicie na kategorie z paskami postępu (wydano vs plan),
  edycja budżetu miesięcznego (planu), przełączanie miesięcy,
- **Dodaj** — transakcja jednym kliknięciem: kategoria, kwota (zawsze
  dodatnia — kierunek wynika z typu kategorii), data, notatka,
- **Kategorie** — typ (wpływ/wydatek), budżet miesięczny, flaga „stała"
  (auto 1. dnia miesiąca), przycisk „Zaksięguj stałe (teraz)", usuwanie,
- **Historia** — seria 12 miesięcy + transakcje wybranego miesiąca
  (edycja i usuwanie pojedynczych wpisów),
- **Lidl - paragony** — paragony **Lidl Plus** synchronizowane z
  **wielu kont** (wspólne zestawienie; każdy paragon oznaczony kontem):
  lista, otwarcie paragonu w nowej karcie (Drukuj → Zapisz jako PDF),
  auto-księgowanie paragonów jako wydatków (albo ręcznie „zaksięguj”),
  usuwanie kopii lokalnej.

## Instalacja

1. **GitHub**: utwórz nowe publiczne repozytorium `HA_Budget_App` i wgraj
   jego zawartość (z rozpakowanego ZIP-a): folder `budget/`, folder
   `.github/` oraz plik `repository.yaml` → commit na `main`.
2. **GitHub Actions**: pierwszy push sam zbuduje obraz Docker do
   `ghcr.io/ravek71/budget-app` — sprawdź workflow **Builder**
   (ok. 1–3 minuty).
3. **Home Assistant** → Add-ony → ⋮ (prawy górny róg) → **Sklep
   z dodatkami** → ⋮ → **Repozytoria niestandardowe** → dodaj:
   `https://github.com/ravek71/HA_Budget_App`
4. **Sklep z dodatkami** → „Budżet domowy" → **Zainstaluj** → **Uruchom**.
5. W sidebarze HA pojawi się panel **Budżet domowy** (ikona portfel) —
   otwórz go i zaczynaj.

> Add-on nie pojawia się w sklepie? Odśwież stronę i w menu sklepu wybierz
> „Szukaj aktualizacji" — obraz musi najpierw istnieć w GHCR.

## Użytkowanie

1. Zakładka **Kategorie** — dodaj pierwsze kategorie, np.:
   - `Wypłata` — wpływ, budżet `8000`, zaznacz **stała**
     (płaca księgowana automatycznie 1. dnia miesiąca);
   - `Czynsz` — wydatek, budżet `2000`, **stała**;
   - `Jedzenie` — wydatek, budżet `1500` (bez flagi stałej).
2. Zakładka **Pulpit** — wpisz budżet miesięczny (plan), np. `5000`.
3. Zakładka **Dodaj** — bieżące transakcje (np. `Jedzenie`, `86,50`,
   notatka „Biedronka").
4. Zakładka **Historia** — seria 12 miesięcy i transakcje miesiąca.

### Wydatki/wpływy stałe

Kategoria z flagą **stała** i budżetem &gt; 0 jest automatycznie
księgowana **1. dnia miesiąca o 00:05** (idempotentnie — brak duplikatów).
Działa dla wpływów (np. wypłata) i wydatków (np. czynsz). Gdyby coś
zabrakło (HA wyłączony 1. dnia), użyj przycisku **Zaksięguj stałe
(teraz)** w zakładce Kategorie. Automatyczne księgowanie można wyłączyć
w opcjach add-onu (`auto_recurring`).

### Paragony Lidl Plus

Funkcja korzysta z **nieoficjalnego** API aplikacji Lidl Plus
(reverse engineered przez społeczność; Lidl może je zmienić lub
zablokować). Dotyczy wyłącznie danych Twojego własnego konta.

1. **Jednorazowo na PC** (Python 3.8+, bez pakietów):
   `python tools\get_lidl_token.py` — otwiera przeglądarkę, logujesz się
   do Lidl Plus normalnie; po przekierowaniu przeglądarka pokaże błąd
   `com.lidlplus.app://callback?code=...` — **skopiuj ten adres** z paska
   i wklej w konsoli. Skrypt wypisze **refresh token**. Dla drugiego
   konta (np. żony) powtórz ten sam krok pod jej loginem.
2. **Panel → zakładka „Lidl - paragony” → dodaj konto**: id (np.
   `konto2`), nazwa (np. „Konto żony”), wklej token. Kont jest tyle,
   ile chcesz — synchronizacja idzie przez wszystkie, a zestawienie
   paragonów jest wspólne (każdy paragon oznaczony kontem). Uszkodzony
   token jednego konta nie przerywa reszty — błąd widać w statusie.
   (Opcja add-onu `lidl_refresh_token` z 0.2.x została automatycznie
   zmigrowana do pierwszego konta; `lidl_country: PL`,
   `lidl_language: pl` nadal globalne.)
3. **„Synchronizuj z Lidl Plus”** — synchronizacja działa w tle
   (status widać w karcie; panel odświeża się sam). Pobiera wszystkie
   dostępne paragony (API Lidl ma zwykle ~12 miesięcy — starszych nie
   ma w źródle).
4. Paragon: **pokaż** → nowa karta z paragonem → „Drukuj → Zapisz jako
   PDF”. **Usuń** kasuje tylko kopię lokalną.
5. **Auto-księgowanie**: zaznacz „auto-księgowanie paragonów jako
   wydatków” i wybierz kategorię (domyślnie auto-detekcja: pierwsza
   kategoria wydatku z „Lidl” w nazwie). Każdy nowy paragon tworzy
   transakcję wydatku (data i kwota z paragonu). Ręcznie: „zaksięguj” /
   „odblokuj” przy każdym paragonie.

Tokeny: access token żyje ~20 min — add-on sam go odświeża per konto.
Refresh token **rotuje** (Lidl zwraca nową wersję przy każdym
odświeżeniu) — add-on przechowuje aktualną wersję w swojej bazie
(tabela `lidl_accounts`) od pierwszej synchronizacji; pole w zakładce
służy do zmiany tokena (np. po wygaśnięciu). Token traktuj jak hasło.

## API (REST)

Panel komunikuje się z add-onem przez REST (przydatne do własnych
automatów przez webhook/REST call):

| Metoda | Ścieżka | Opis |
|---|---|---|
| GET | `/api/status` | wersja, bieżący miesiąc, budżet miesięczny |
| GET | `/api/summary?year=&month=` | podsumowanie miesiąca + transakcje |
| GET | `/api/history` | seria 12 miesięcy |
| GET | `/api/categories` | lista kategorii |
| POST | `/api/categories` | `{"name","kind":"income|expense","recurring","monthly_budget"}` |
| PUT | `/api/categories/<key>` | aktualizacja (nazwa zmienia klucz — transakcje migrują) |
| DELETE | `/api/categories/<key>` | usunięcie (400, jeśli są transakcje) |
| POST | `/api/transactions` | `{"category","amount","date?","note?"}` |
| DELETE | `/api/transactions/<id>` | usunięcie transakcji |
| PUT | `/api/total_budget` | `{"amount"}` — budżet miesięczny (plan) |
| POST | `/api/recurring` | zaksięguj stałe bieżącego miesiąca teraz |
| GET | `/api/receipts` | paragony (bez HTML) + status + konta + auto-księgowanie |
| POST | `/api/receipts/sync` | start synchronizacji z Lidl Plus (w tle) |
| GET | `/api/receipts/<id>/print` | HTML paragonu (do druku/PDF w przeglądarce) |
| DELETE | `/api/receipts/<id>` | usunięcie kopii lokalnej paragonu |
| PUT | `/api/receipts/auto_book` | `{"enabled","category"?}` — auto-księgowanie paragonów |
| POST | `/api/receipts/<id>/book` | `{"category"?}` — zaksięguj paragon jako wydatek |
| DELETE | `/api/receipts/<id>/book` | usuń transakcję z paragonu (paragon zostaje) |
| GET | `/api/lidl/accounts` | lista kont Lidl Plus |
| POST | `/api/lidl/accounts` | `{"id","name","token"}` — dodaj konto |
| PUT | `/api/lidl/accounts/<id>` | `{"name"?,"token"?}` — zmiana konta |
| DELETE | `/api/lidl/accounts/<id>` | usunięcie konta |
| GET | `/healthz` | status + wersja |

## Dane

SQLite w `/data/budget.db` (wolumen add-onu) — aktualizacja add-onu nie
kasuje danych. Usunięcie add-onu kasuje wolumen; backup = kopia pliku.
