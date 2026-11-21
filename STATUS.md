# Status — HA_Budget_App (app add-on „Budżet domowy")

Stan na: 2026-11-21. U usera działa **0.1.2** (potwierdzone: „Działa");
na dysku gotowe **0.2.0** (testy zielone): **Paragony Lidl Plus** —
nowa tabela `receipts`, zakładka „Paragony”, sync w tle z nieoficjalnego
API (`app/lidl.py`, `app/lidlsync.py`), opcje `lidl_refresh_token` /
`lidl_country` / `lidl_language`, skrypt `tools/get_lidl_token.py`
(jednorazowy login w przeglądarce → token do opcji).
Kluczowa lekcja: panel ingress HA żyje w iframe pod
`/api/hassio_ingress/<token>/` — HA odcina cały ten prefix przed proxy do
appa, więc JS panela musi dzwonić **ścieżkami względnymi do katalogu
panelu** (`API_DIR` z `location.pathname`), nigdy absolutnie.

## Gotowe
- Add-on `budget/`: `config.yaml` (ingress, port 8099, watchdog `/healthz`,
  opcje `log_level` + `auto_recurring`), `Dockerfile` (python:3.12-slim,
  wzorzec 1:1 z HA_News), `requirements.txt` (tylko flask), `app/`
  (`__init__`, `__main__`, `config`, `data`, `server`, `panel`),
  `translations/pl.yaml`.
- CI: `.github/workflows/builder.yaml` + `build-app.yaml` (kopia z HA_News)
  — build obrazu `ghcr.io/ravek71/budget-app` (amd64 + aarch64).
- `repository.yaml` — repozytorium niestandardowe dla HACS.
- Testy: `py_compile` = 0; test funkcjonalny całego API (Flask test client,
  tymczasowa baza) = `APP_OK` (kategorie, duplikaty, transakcje, walidacje,
  budżety, auto-stałe idempotentne, historia, panel).
- ZIP do wgrania: `C:\AI_Project\HA_Budget_App.zip`.

## Struktura plików
```
HA_Budget_App/
├── .github/workflows/{builder,build-app}.yaml
├── budget/
│   ├── app/{__init__,__main__,config,data,server,panel}.py
│   ├── translations/pl.yaml
│   ├── config.yaml
│   ├── Dockerfile
│   └── requirements.txt
├── repository.yaml
├── .gitignore
├── CHANGELOG.md
├── README.md
└── STATUS.md
```

## Kluczowe decyzje
- **App add-on, nie HACS** — decyzja usera (2026-11-20): pełny panel
  ingress (Pulpit/Dodaj/Kategorie/Historia), zero helperów, wzorzec jak HA_News.
- **Dane od zera** — stara integracja HACS nie miała jeszcze danych.
- **Port 8099 w kontenerze** — identyczny wzorzec jak HA_News
  (`ports: 8099/tcp: 8080` w config.yaml; app słucha 8099).
- **Stałe = wpływy i wydatki** — kategoria `recurring` + budżet > 0 →
  auto-księgowanie 1. dnia miesiąca o 00:05 (idempotentnie) + przycisk
  „Zaksięguj stałe (teraz)" w panelu; wyłączenie opcją `auto_recurring`.
- **Nazwy kategorii zamiast slugów** — slug generuje sama apka
  (`_unique_key`), user nigdy nie wpisuje klucza (lekcja z HACS 0.1.x).
- `data.py` przeniesiona 1:1 z projektu HACS (testowana) + rozszerzenie
  `apply_recurring` o wpływy.

## Zamarznięte / w tle
- `C:\AI_Project\HA_Budget` (integracja HACS 0.1.4, repo `ravek71/HA_Budget`)
  — ZAMROŻONE, nie ruszamy; opcjonalnie user usuwa integrację z HA i repo.
- `C:\AI_Project\HA_News` (1.2.2) — w tle czeka wgranie na GitHub.
- `C:\AI_Project\HA_Budget\Home Budget` — repo usera, nietknięte.

## Następne kroki (user)
1. GitHub: nowe publiczne repo `ravek71/HA_Budget_App` → wgrać zawartość
   `C:\AI_Project\HA_Budget_App.zip` (folder `budget/`, `.github/`,
   `repository.yaml`, README/CHANGELOG/STATUS, .gitignore) → commit.
2. Odczekać na workflow **Builder** (GHCR `ghcr.io/ravek71/budget-app`).
3. HA → Add-ony → ⋮ → Sklep z dodatkami → ⋮ → Repozytoria niestandardowe →
   `https://github.com/ravek71/HA_Budget_App` → Zainstaluj „Budżet domowy"
   → Uruchom.
4. Panel w sidebarze (ikona portfel) → kategorie → budżet → transakcje.
5. (Opcjonalnie) usunąć starą integrację HACS „Budżet domowy" z HA
   (Ustawienia → Urządzenia i usługi → Budżet domowy → Usuń) i repo
   `ravek71/HA_Budget`.
