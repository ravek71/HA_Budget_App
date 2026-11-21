# Status — HA_Budget_App (app add-on „Budżet domowy")

Stan na: 2026-11-21. U usera działa **0.2.0/0.2.1** (potwierdzone:
„działa!" — token i sync OK, paragony pobierane); na dysku gotowe
**0.3.1** (testy zielone): fix paginacji syncu (API capuje stronę na
~25 — teraz aż do pustej strony), wiele kont Lidl Plus (tabela
`lidl_accounts`, zakładka „Lidl - paragony” — tylko nazwa + token,
wspólne zestawienie, uszkodzony token jednego konta nie rzuca reszty),
auto-księgowanie paragonów jako wydatków (przełącznik + kategoria,
albo ręcznie „zaksięguj/odblokuj”), lista kont żywa z bazy (nowe konto
widoczne od razu), status sync pogrubiony, `lidl_refresh_token`
usunięte z konfiguracji add-onu, migracja starego tokena do konta.

Zweryfikowane na żywo (2026-11-21, od maszyny usera):
- URL autoryzacyjny (`/connect/authorize` + PKCE, Country=PL, language=pl-PL)
  jest AKCEPTOWANY: `302 → accounts.lidl.com/Account/Login?ReturnUrl=...`
  (to „ospała strona logowania" — ładowanie wolne, bo sieć usera
  inspekcjonuje TLS — self-signed cert w łańcuchu; przeglądarka przechodzi,
  urllib nie).
- Skrypt ma już fallback SSL (bez weryfikacji certyfikatu, ostrzeżenie
  na stderr) + instrukcję DevTools (F12 → Sieć → request „callback”).
Kluczowa lekcja: panel ingress HA żyje w iframe pod
`/api/hassio_ingress/<token>/` — HA odcina cały ten prefix przed proxy do
appa, więc JS panela musi dzwonić **ścieżkami względnymi do katalogu
panelu** (`API_DIR` z `location.pathname`), nigdy absolutnie.

## Gotowe
- Add-on `budget/`: `config.yaml` (ingress, port 8099, watchdog `/healthz`,
  opcje `log_level` + `auto_recurring` + `lidl_country`/`lidl_language`),
  `Dockerfile` (python:3.12-slim, wzorzec 1:1 z HA_News),
  `requirements.txt` (tylko flask), `app/` (`__init__`, `__main__`,
  `config`, `data`, `server`, `panel`, `lidl`, `lidlsync`),
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
│   ├── app/{__init__,__main__,config,data,server,panel,lidl,lidlsync}.py
│   ├── translations/pl.yaml
│   ├── config.yaml
│   ├── Dockerfile
│   └── requirements.txt
├── tools/{get_lidl_token.py,debug_lidl.py}
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

## Następne kroki (user) — wdrożenie 0.3.1
1. GitHub Web UI (repo `ravek71/HA_Budget_App`, gałąź `main`): wgraj
   zawartość `C:\AI_Project\HA_Budget_App.zip` (całość — nadpisuje pliki,
   commit message: „0.3.1”). Kluczowe: `budget/config.yaml` ma
   `version: "0.3.1"` (tag obrazu GHCR = wersja z config.yaml).
2. Actions → **Builder** → zielony (~2 min) → obraz
   `ghcr.io/ravek71/budget-app:0.3.1`.
3. HACS (⋮ → Check for updates, jeśli nie widać) → Add-ony → „Budżet
   domowy" → **Update** (0.3.0 → 0.3.1) → panel F5.
4. Panel → zakładka **Lidl - paragony**: stare konto z 0.2.x zostanie
   zmigrowane automatycznie (token z opcji → tabela `lidl_accounts`).
   Ewentualnie dodaj drugie konto (id + nazwa + token z
   `tools/get_lidl_token.py` pod drugim loginem).
5. Ustawienia paragonów: zaznacz auto-księgowanie + kategoria (albo
   auto-detekcja) → Zapisz → **Synchronizuj z Lidl Plus**.
6. (Opcjonalnie) usunąć starą integrację HACS „Budżet domowy" z HA
   (Ustawienia → Urządzenia i usługi → Budżet domowy → Usuń) i repo
   `ravek71/HA_Budget`.
