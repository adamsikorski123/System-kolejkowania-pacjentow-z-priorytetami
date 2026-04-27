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


najpierw run.py -> ngrok http 5000  (w venv)