# Changelog

## 0.3.5 (2026-11-23)

- **Sortowanie tabeli paragonów** (zakładka „Lidl - paragony"): klik w
  nagłówek kolumny **Data / Konto / Sklep / Pozycje / Kwota** sortuje po
  tej kolumnie; ponowne kliknięcie odwraca kierunek (strzałka ▼/▲ w
  nagłówku pokazuje aktywną kolumnę i kierunek). Domyślnie: Data ▼
  (najnowsze na górze, jak wcześniej). Konto sortuje po NAZWIE konta.
- **Paginacja tabeli paragonów**: wybór liczby wpisów na stronę
  (**10 / 25 / 50 / 100**, domyślnie 25), przyciski
  „← Poprzednia / Następna →" + „strona X z Y" i licznik „razem: N
  paragonów" (poprawna polska odmiana). Sortowanie i strona przetrwają
  odświeżanie podczas synchronizacji.
- Zmiana czysto panelowa (JS po stronie klienta — API bez zmian),
  więc działa też na telefonie (mały flex, przyciski dotykowe).

## 0.3.4 (2026-11-23)

- **Fix: lista nie domykała się, gdy backend konta ignoruje parametr
  `skip`.** Nieregularne API Lidl Plus ma DWA pokolenia stronicowania
  i milcząco ignoruje parametr, którego nie zna: `?skip=&take=`
  (bieżąca apka 17.9.3) oraz `?pageNumber=N&onlyFavorite=false`
  (legacy, 1-based; rozmiar strony ustala serwer). Sync teraz **sam
  wykrywa mechanizm przy każdym przebiegu**: sonda drugiej strony
  stylem `skip`, a gdy nie przesuwa listy — sonda stylem `pageNumber`;
  zgodnie z wynikiem przechodzi listę (tryb `skip` lub `page`). Gdy
  oba parametry są ignorowane i strona 1 jest pełna — status pokazuje
  jawny błąd z instrukcją diagnostyki zamiast cicho przerywać po
  ~25 paragonach.
- `PAGE_TAKE = 25` (faktyczny cap serwera) — strona krótsza niż cap
  naprawdę oznacza koniec listy (wg specyfikacji apki 17.9.3: koniec,
  gdy strona < `take`).
- Koniec pętli: `totalCount` z wrappera (gdy API go zwraca), strona
  całkowicie powtórzona, pusta strona albo limit 200 stron. Fix 0.3.3
  zostaje: pozycje znane z bazy NIE zatrzymują pętli.
- `lidl.list_tickets` przyjmuje `page_number` (legacy, 1-based) oprócz
  `skip`/`take`; `take` domyślnie 25.
- Testy: nowy scenariusz „legacy API" — `skip` ignorowany,
  `pageNumber` działa, 30 pozycji w 2 stronach, wrapper `totalCount`;
  sync przechodzi listę w całości.

## 0.3.3 (2026-11-23)

- **Fix: sync przerywał się po pierwszej stronie, gdy te paragony były już
  w bazie.** Warunek „strona bez nowych = koniec listy" (0.3.2) mieształ
  dwa pojęcia: „już w bazie z poprzedniego syncu" i „już pobrane w tym
  przebiegu". Przy wcześniejszym częściowym pobraniu (np. ~25 paragonów)
  strona 1 była w całości znana z bazy → pętla kończyła się od razu,
  mimo że `skip` mógłby pobrać strony 2..N. Teraz koniec = strona
  CAŁKOWICIE powtórzona w tym przebiegu (API ignoruje `skip`) albo
  osiągnięcie `totalCount` zwracanego przez API; paragony znane z bazy
  są tylko pomijane w szczególe (bez ponownego pobierania).
- `lidl.list_tickets` zwraca teraz `(items, totalCount)` — obsłużony
  oficjalny format-wrapper listy (`page`/`size`/`totalCount` + `tickets`),
  jakiego używa nowa apka Lidl Plus (v17.9.3), i format-tablicy
  (starszy). `totalCount` = autorytatywny koniec listy, gdy API go daje.
- `tools/debug_lidl.py`: sonda paginacji rozszerzona o [7] `pageNumber`
  (stary parametr — czy jeszcze żywy?) i wykrywanie FORMATU odpowiedzi
  (wrapper z metadanymi vs tablica) — output pokaże, jak dokładnie
  stronicuje konto usera.

## 0.3.2 (2026-11-22)

- **Fix: sync w 0.3.1 mógł wisnąć w nieskończoność** („paragony nie są
  pobierane”). Pętla stron kończyła się dopiero na pustej stronie, a API
  Lidl może ignorować parametr `skip` — wtedy każda strona zwraca te same
  pozycje. Teraz: strona bez ŻADNEGO nowego paragonu = koniec listy
  (zabezpieczenie przed pętlą) + twardy limit 200 stron. Status pokazuje
  numer strony („strona 2 (od 25)..."), więc postęp widać od razu.
- `tools/debug_lidl.py`: nowa sonda paginacji (punkty [5]/[6]) — pokazuje,
  czy `skip` przesuuje listę, czy API ją ignoruje (decyduje o dalszej
  naprawie, jeśli lista wciąż się nie domyka).

## 0.3.1 (2026-11-21)

- **Fix: sync pobierał tylko pierwszą stronę paragonów (~25)**. API Lidl
  zwraca mniej pozycji na stronę niż zażądane (własny limit), a pętla
  paginacji przerywała się przy `len(page) < take`. Teraz przesuwania
  o faktyczną długość strony i koniec tylko na pustej stronie.
- Lista kont w zakładce „Lidl - paragony" ładowana na bieżąco z bazy
  (dawniej ze statusu synchronizacji — nowe konto było niewidoczne do
  czasu syncu/restartu; stąd „okno się nie odświeża").
- Dodawanie konta: tylko **nazwa + token** (id generowane automatycznie
  z nazwy, np. „Konto żony" → `konto-żony`; duplikat nazwy = `konto-żony-2`).
- Status synchronizacji („Synchronizacja: …") pokazywany **pogrubioną**
  czcionką.
- Usunięto parametr `lidl_refresh_token` z konfiguracji add-onu — konta
  Lidl Plus zarządza się wyłącznie w panelu. Migracja legacy (settings w
  bazie) zostaje; `lidl_country`/`lidl_language` nadal w opcjach.
- Usunięty opis pod tabelą paragonów.

## 0.3.0 (2026-11-21)

- **Wiele kont Lidl Plus**: nowa tabela `lidl_accounts` (id, nazwa, refresh
  token). Zakładka „Lidl - paragony” — dodawanie/usuwanie dowolnej liczby
  kont, zmiana tokena bez usuwania konta. Synchronizacja idzie przez wszystkie
  konta; uszkodzony token jednego konta nie przerywa reszty (błąd w statusie).
  Zestawienie paragonów jest wspólne — każdy paragon oznaczony jest kontem.
- **Auto-księgowanie paragonów**: każdy nowy paragon po synchronizacji tworzy
  transakcję wydatku (data i kwota z paragonu, notatka „Paragon Lidl …”).
  Kategoria: ustawiona w zakładce (lista kategorii wydatków) albo
  auto-detekcja (pierwsza kategoria wydatku z „Lidl” w nazwie). Przełącznik
  i kategoria w zakładce; ręcznie: przyciski „zaksięguj” / „odblokuj” przy
  każdym paragonie. „Odblokuj” usuwa transakcję, paragon zostaje.
- Token z wersji 0.2.x (opcja `lidl_refresh_token` / settings) migrowany
  automatycznie do pierwszego konta.
- Zakładka „Paragony” → „Lidl - paragony”.
- Endpoints: `GET/POST /api/lidl/accounts`, `PUT/DELETE
  /api/lidl/accounts/<id>`, `PUT /api/receipts/auto_book`,
  `POST /api/receipts/<id>/book`, `DELETE /api/receipts/<id>/book`.
- `GET /api/receipts` zwraca też `accounts`, `auto_book`, `auto_category`.

## 0.2.1 (2026-11-21)

- Diagnostyka błędu listy paragonów: komunikat z podglądem odpowiedzi
  serwera (300 znaków) + tolerancja na wrapper listy (`tickets`/`items`/
  `data`/`result`/`content`). Nowy skrypt `tools/debug_lidl.py`
  (token, lista v2, lista v3, detail).

## 0.2.0 (2026-11-21)

- **Paragony Lidl Plus**: nowa zakładka „Paragony” w panelu. Synchronizacja
  (w tle, z listy do szczegółów) z nieoficjalnego API aplikacji Lidl Plus —
  paragony trafiają do nowej tabeli `receipts` w bazie SQLite (data, sklep,
  kwota, pozycje, HTML paragonu, surowy JSON). Przeglądanie, otwarcie
  paragonu w nowej karcie (Drukuj → Zapisz jako PDF) i usuwanie kopii lokalnej.
- Autoryzacja: jednorazowy login w przeglądarce (skrypt
  `tools/get_lidl_token.py` — czysty Python, bez pakietów) → refresh token
  wklejany do opcji add-onu `lidl_refresh_token`. Add-on sam odświeża access
  token i przechowuje **rotowany** refresh token w bazie (odporna na
  restarty; opcja = zapas/ponowne wejście).
- Opcje add-onu: `lidl_refresh_token`, `lidl_country` (domyślnie PL),
  `lidl_language` (domyślnie pl).
- Nowe moduły: `app/lidl.py` (klient API, stdlib), `app/lidlsync.py`
  (synchronizacja w tle, retry 401/429); endpoints `GET/POST /api/receipts`,
  `GET /api/receipts/<id>/print`, `DELETE /api/receipts/<id>`.

## 0.1.3 (2026-11-20)

- Historia: edycja transakcji (nie tylko usuwanie). Przycisk „edytuj"
  otwiera formularz (zakładka Dodaj) z podpiętymi danymi — można zmienić
  kategorię, kwotę, datę i notatkę; „Anuluj" wraca do historii.
  Nowy endpoint `PUT /api/transactions/<id>` + `update_transaction`
  w warstwie danych (walidacja kategorii/kwoty/daty, id się nie zmienia).

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
