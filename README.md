# System-kolejkowania-pacjentow-z-priorytetami

<p align="center">
  <img src="app/static/img/pg_logo.jpg" alt="Logo Politechniki Gdańskiej" height="800"/>
  &nbsp;&nbsp;&nbsp;
  <img src="app/static/img/kib_logo.png" alt="Logo KIB" height="800"/>
</p>


---
| | |
|---|---|
| **Przedmiot** | RAIM – Rozwój aplikacji internetowych w medycynie (2025/2026) |
| **Temat** | Temat 2 – System kolejkowania pacjentów z priorytetami |
| **Etap** | Etap 1 – Implementacja bazowa (kolejka FIFO) |
| **Rok studiów** | 3|
| **Prowadzący** | dr inż. Anna Jezierska |
| **Autorzy** | Adam Sikorsi, Mateusz Grochowalski |
| **Uczelnia** | Politechnika Gdańska, Wydział ETI |
| **Katedra** | Katedra Inżynierii Biomedycznej (KIB) |

---

## Spis treści

1. [Analiza potrzeb i wymagań klinicznych](#1-analiza-potrzeb-i-wymagań-klinicznych)
2. [Projekt architektury systemu](#2-projekt-architektury-systemu)
3. [Aktualny stan implementacji (zgodny z kodem)](#3-aktualny-stan-implementacji-zgodny-z-kodem)
4. [Bazy danych (aktualna struktura)](#4-bazy-danych-aktualna-struktura)
5. [Uruchomienie projektu (lokalnie)](#5-uruchomienie-projektu-lokalnie)
6. [Zarządzanie kontami użytkowników](#6-zarządzanie-kontami-użytkowników)
7. [Główne endpointy API](#7-główne-endpointy-api)
8. [Uwagi wdrożeniowe](#8-uwagi-wdrożeniowe)

---

## 1. Analiza potrzeb i wymagań klinicznych

### 1.1 Identyfikacja problemu

W środowisku szpitalnym, a sczególnie w izbach przyjęć (SOR), poradniach i oddziałach intensywnej terapii - zarządzanie kolejką pacjentów jest istotnym problemem. Tradycyjne podejście FIFO (first-in, first-out) bez uwzględnienia stanu klinicznego pacjenta może prowadzić do poważnych zagrożeń zdrowotnych: pacjent w stanie zagrożenia życia może oczekiwać za pacjentem z mniej groźną dolegliwością.

Niniejszy projekt symuluje system kolejkowania pacjentów oparty na priorytetach klinicznych, który w kolejnych etapach zostanie rozszerzony o race condition i mechanizm aging.

**Etap 1** implementuje podstawowy wariant kolejki **FIFO** za pomocą losowej generacji pacjentów (według rozkładu Poissona) i obsługi przez operatora.

### 1.2 Określenie użytkowników systemu


**Pacjent** - Osoba dodawana do kolejki, dodanie do kolejki, podgląd realizacji przyjęcia.

**Operator medyczny** - Pielęgniarka/lekarz przyjmujący, przyjęcie następnego pacjenta, aktualizacja statusu.

### 1.3 Analiza ryzyk

| # | Ryzyko | Prawdopodobieństwo | Wpływ | Redukcja |
|---|--------|--------------------|-------|-----------|
| R1 | Race condition przy jednoczesnym pobieraniu pacjenta przez wielu operatorów | Wysokie | Krytyczny | Mechanizm blokad|
| R2 | Starvation pacjentów z niskim priorytetem (ryzyko nieprzyjęcia) | Wysokie | Wysoki | Mechanizm aging|
| R3 | Utrata danych kolejki przy restarcie systemu | Wysokie | Wysoki | Zapis danych w SQLite |
| R4 | Błędy przy aktualizacji priorytetów| Średnie | Wysoki | Wersjonowanie rekordów|
| R5 | Przeciążenie systemu przy dużym napływie pacjentów | Niskie | Średni | Logi i monitoring|

---

## 2. Projekt architektury systemu

### Uruchamianie przez `kolejka.local` (Windows)

1. Otwórz jako administrator plik:
  `C:\Windows\System32\drivers\etc\hosts`
2. Dodaj linię:
  `127.0.0.1 kolejka.local`
3. Uruchom aplikację i wejdź w przeglądarce na:
  `http://kolejka.local`

> Jeśli aplikacja ma być dostępna też dla innych komputerów w sieci, każdy z nich musi mieć wpis w `hosts` wskazujący na IP komputera-serwera.

### 2.1 Przegląd architektury

System zbudowany jest w architekturze **klient-serwer** z komunikacją REST API:

```
┌─────────────────────────────────────────────────┐
│                    FRONTEND                     │
│              HTML + JavaScript + CSS            │
└──────────────────┬──────────────────────────────┘
                   │  REST API
┌──────────────────▼──────────────────────────────┐
│                  BACKEND (Flask/Python)         │
│                                                 │
│  ┌────────────┐   ┌──────────────────────────┐  │
│  │  Routes    │   │     QueueManager         │  │
│  │  (REST)    │──▶│  (kolejka FIFO / prio)  │   │
│  └────────────┘   └──────────┬───────────────┘  │
│                              │                  │
│  ┌───────────────────────────▼────────────────┐ │
│  │        SQLAlchemy ORM + SQLite             │ │
│  │         (pacjenci, kolejka)                │ │
│  └────────────────────────────────────────────┘ │
│                                                 │
│  ┌─────────────────────────────────────────────┐│
│  │             Logging systemowy               ││
│  └─────────────────────────────────────────────┘│
└─────────────────────────────────────────────────┘
```

### 2.2 Model danych (Etap 1)

```
Pacjent
├── id (int)
├── imię (string)
├── nazwisko (string)
├── priorytet
├── czas przybycia (datetime)
└── status


QueueEntry
├── id (int)
├── priorytet 
├── czas przybycia (datetime)
├── czas w kolejce (datetime)
└── czas przyjęcia (datetime)

```

## 3. Aktualny stan implementacji (zgodny z kodem)

- Kolejka pacjentów działa na priorytetach (1–5), z możliwością ręcznej zmiany priorytetu w UI (`-` / `+`).
- Lista pacjentów jest wspólna dla wszystkich użytkowników.
- Przyjęcie pacjenta działa per użytkownik (oddzielny stan bieżącego pacjenta i cooldown dla zalogowanego operatora).
- Zmiany kolejki są odświeżane cyklicznie po stronie frontend (polling endpointu stanu).
- Dane są utrwalane w SQLite.

## 4. Bazy danych (aktualna struktura)

Aplikacja używa dwóch oddzielnych plików SQLite:

- `users.db` – konta użytkowników (login, hasło zahashowane),
- `patients.db` – dane pacjentów i kolejki.

> Bazy są tworzone automatycznie przy pierwszym uruchomieniu aplikacji.

## 5. Uruchomienie projektu (lokalnie)

1. Wejdź do katalogu projektu:
   `cd c:\Users\adams\OneDrive\Pulpit\RAIM`
2. Utwórz i aktywuj virtualenv:
   - `python -m venv .venv`
   - `.\.venv\Scripts\Activate.ps1`
3. Zainstaluj zależności:
   - `python -m pip install --upgrade pip`
   - `python -m pip install -r requirements.txt`
4. Uruchom aplikację:
   - `python run.py`
5. Otwórz:
   - `http://127.0.0.1:5000`
   - lub `http://kolejka.local` (jeśli skonfigurowano wpis w `hosts`).

## 6. Zarządzanie kontami użytkowników

Do zarządzania użytkownikami użyj:
`python app/add_account.py`

Dostępne komendy:
- `add` – dodanie konta,
- `delete` – usunięcie konta,
- `list` – lista kont,
- `exit` – wyjście.

## 7. Główne endpointy API

- `GET /api/queue/state` – pełny stan kolejki (w tym `patients`, `current`, `wait_time`),
- `POST /api/queue/admit` – przyjęcie kolejnego pacjenta przez aktualnego użytkownika,
- `POST /api/queue/change-priority` – zmiana priorytetu pacjenta,
- `POST /api/queue/reset` – reset kolejki,
- `GET /api/queue/version` – uproszczony stan wersji kolejki.

## 8. Uwagi wdrożeniowe

- Aplikacja domyślnie działa na porcie `5000` (można zmienić przez `PORT`).
- Do testów publicznego dostępu można użyć:
  - uruchomienia aplikacji lokalnie,
  - `ngrok http 5000`.

---

## Notatki deweloperskie

1. **Środowisko**: Python 3.10+, Flask, SQLite
2. **Struktura projektu**:
   - `app/` – kod aplikacji Flask,
   - `migrations/` – migracje bazy danych (Alembic),
   - `tests/` – testy jednostkowe i integracyjne,
   - `venv/` – virtualenv (nie dołączaj do repozytorium).
3. **Zarządzanie zależnościami**: Użyj `pip` i `requirements.txt` lub `pipenv`/`poetry`.
4. **Uruchamianie aplikacji**: `flask run` lub `python -m flask run`.
5. **Debugowanie**: Włącz tryb debugowania w Flask (`app.run(debug=True)`) lub użyj zewnętrznych narzędzi (np. `pdb`, `werkzeug`).
6. **Testowanie**: Użyj wbudowanego narzędzia do testowania Pythona lub frameworków takich jak `pytest`.
7. **Dokumentacja**: Komentuj kod i używaj narzędzi do generowania dokumentacji (np. `Sphinx`).
8. **Wersjonowanie**: Użyj systemu kontroli wersji (np. `git`) i stosuj się do dobrych praktyk (np. commit message convention).
9. **CI/CD**: Rozważ użycie narzędzi do ciągłej integracji i dostarczania (np. GitHub Actions, Travis CI).
10. **Monitorowanie i logowanie**: Zaimplementuj mechanizmy monitorowania i logowania błędów (np. `Sentry`, `Loggly`).