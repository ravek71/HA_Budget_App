# Changelog

## 0.1.2 (2026-11-20)

- Fix (poprawka 0.1.1): wywołania API panelu są teraz **względne do
  katalogu panelu** (`API_DIR` z `location.pathname`), a nie absolutne.
  Zweryfikowane na żywym ingressie: panel w iframe
  `/api/hassio_ingress/<token>/` → fetch `api/categories` z tego iframe →
  `200`. Wersja 0.1.1 (pierwszy fix) została zbudowana, zanim poprawiono
  logikę — stąd nowa wersja.

## 0.1.1 (2026-11-20)

- Fix: panel dzwonił na API ścieżkami absolutnymi (`/api/...`) — przez
  ingress HA (panel w iframe pod `/api/hassio_ingress/<token>/`) takie
  wywołania trafiały do rdzenia HA i wracały **404**, przez co panel
  pokazywał puste dane. Teraz wszystkie wywołania są względne do
  katalogu panelu (`/api/hassio_ingress/<token>/api/...` → app `/api/...`)
  — zweryfikowane na żywym ingressie.

## 0.1.0 (2026-11-20)

- Wersja startowa **app add-on** (przeniesienie projektu z formy integracji
  HACS `ravek71/HA_Budget` — dane startują od zera).
- Panel ingress w HA (sidebar, ikona portfel): Pulpit / Dodaj / Kategorie /
  Historia.
- Pulpit: wpływy, wydatki, bilans, pozostało z budżetu, budżet miesięczny
  (plan) edytowalny, wykres 12 miesięcy, rozbicie na kategorie (paski
  wydano vs plan), przełączanie miesięcy.
- Dodaj: kategoria (grupy Wpływy/Wydatki), kwota, data, notatka.
- Kategorie: typ, budżet miesięczny, flaga „stała" (auto-księgowanie
  1. dnia miesiąca o 00:05 — wpływy i wydatki, idempotentnie), przycisk
  „Zaksięguj stałe (teraz)", edycja i usuwanie.
- Historia: seria 12 miesięcy + transakcje miesiąca z usuwaniem.
- REST API (`/api/*`) + `/healthz`; dane w SQLite `/data/budget.db`.
- CI: workflow **Builder** buduje obraz `ghcr.io/ravek71/budget-app`.
