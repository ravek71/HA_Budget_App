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
  (z usuwaniem pojedynczych wpisów).

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
| GET | `/healthz` | status + wersja |

## Dane

SQLite w `/data/budget.db` (wolumen add-onu) — aktualizacja add-onu nie
kasuje danych. Usunięcie add-onu kasuje wolumen; backup = kopia pliku.
