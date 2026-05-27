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
3. [Symulacja zaburzeń](#3-symulacja-zaburzeń)
4. [Instrumentacja](#4-instrumentacja)
5. [Omówienie zagadnień współbieżności (race condition)](#5-omówienie-zagadnień-współbieżności-race-condition)


---

## 1. Analiza potrzeb i wymagań klinicznych

### 1.1 Identyfikacja problemu

W środowisku szpitalnym, a sczególnie w izbach przyjęć (SOR), poradniach i oddziałach intensywnej terapii - zarządzanie kolejką pacjentów jest istotnym problemem. Tradycyjne podejście FIFO (first-in, first-out) bez uwzględnienia stanu klinicznego pacjenta może prowadzić do poważnych zagrożeń zdrowotnych: pacjent w stanie zagrożenia życia może oczekiwać za pacjentem z mniej groźną dolegliwością.

Niniejszy projekt symuluje system kolejkowania pacjentów oparty na priorytetach klinicznych, który w kolejnych etapach zostanie rozszerzony o race condition i mechanizm aging.

**Etap 1** implementuje podstawowy wariant kolejki **FIFO** za pomocą losowej generacji pacjentów (według rozkładu Poissona) i obsługi przez operatora.
**Etap 2** Dynamiczne zmiany **priorytetów** przez wielu operatorów.

### 1.2 Określenie użytkowników systemu


**Pacjent** - Osoba dodawana do kolejki, dodanie do kolejki, podgląd realizacji przyjęcia.

**Operator medyczny** - Pielęgniarka/lekarz przyjmujący, przyjęcie następnego pacjenta, aktualizacja statusu.

### 1.3 Analiza ryzyk

| # | Ryzyko | Prawdopodobieństwo | Wpływ | Redukcja |
|---|--------|--------------------|-------|-----------|
| R1 | Race condition przy jednoczesnym pobieraniu pacjenta przez wielu operatorów oraz zmian priorytetu| Wysokie | Krytyczny | Mechanizm blokad|
| R2 | Starvation pacjentów z niskim priorytetem (ryzyko nieprzyjęcia) | Wysokie | Wysoki | Mechanizm aging|
| R3 | Utrata danych kolejki przy restarcie systemu | Wysokie | Wysoki | Zapis danych w SQLite |
| R4 | Błędy przy aktualizacji priorytetów| Średnie | Wysoki | Wersjonowanie rekordów|
| R5 | Przeciążenie systemu przy dużym napływie pacjentów | Niskie | Średni | Logi i monitoring|

---

## 2. Projekt architektury systemu

### Uruchamianie lokalnie przez `http://127.0.0.1:5000`
### Uruchamianie zdalnie przez `https://system-kolejkowania-pacjentow-z-xuty.onrender.com`


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

---
## 3. Symulacja zaburzeń 



Podczas realizacji projektu napotkano dwa istotne problemy charakterystyczne dla systemów kolejkowych i współbieżnych: starvation oraz race condition. 


### 3.1 Starvation


Starvation oznacza sytuację, w której element o niższym priorytecie może być przez długi czas pomijany, ponieważ system stale preferuje elementy o priorytecie wyższym. W kontekście naszego projektu oznacza to, że pacjent o niskim priorytecie mógł oczekiwać znacznie dłużej, jeśli w kolejce nieustannie pojawiali się pacjenci pilniejsi. Zjawisko to jest dobrze znane z teorii planowania zadań w systemach operacyjnych i stanowi naturalne ryzyko w algorytmach priorytetowych.


### 3.2 Race Condition


Drugim zaobserwowanym problemem był race condition, czyli błąd współbieżności pojawiający się wtedy, gdy dwie osoby jednocześnie modyfikują te same dane. W naszym przypadku dotyczyło to równoczesnej zmiany priorytetu tego samego pacjenta przez dwóch użytkowników systemu. Przykładowo, jeśli pacjent miał ustawiony priorytet 4, jedna osoba mogła kliknąć obniżenie priorytetu, a druga jego podwyższenie. Ze względu na opóźnienie aktualizacji danych w bazie oraz brak pełnej synchronizacji widoków, system mógł chwilowo pokazać priorytet 3, a następnie przeskoczyć na 5. Tego typu zachowanie jest przykładem konfliktu współbieżnych zapisów i pokazuje, że końcowy stan danych zależał od kolejności wykonania operacji.



Opisane problemy pokazują, że projektowanie systemów kolejkowych nie ogranicza się jedynie do ustalenia zasad obsługi pacjentów, ale wymaga również uwzględnienia sprawiedliwości działania algorytmu oraz odporności na jednoczesny dostęp wielu użytkowników. W praktyce ograniczanie starvation może wymagać zastosowania mechanizmów zwiększania priorytetu wraz z czasem oczekiwania, natomiast redukcja race condition wymaga lepszej kontroli współbieżności, na przykład blokad, transakcji lub mechanizmów wykrywania konfliktów zapisu.


---

## 4. Instrumentacja


W analizie wydajności systemu instrumentacja oznacza zastosowanie dodatkowych mechanizmów rejestrujących zdarzenia oraz czasy ich występowania w trakcie działania aplikacji. Jej celem jest zebranie danych, które pozwalają mierzyć i oceniać zachowanie systemu pod względem wydajnościowym, na przykład czas obsługi operacji, czas oczekiwania lub opóźnienia komunikacyjne.


### 4.1 API latencja last

W odniesieniu do latencji instrumentacja umożliwia wyznaczenie czasu potrzebnego na realizację konkretnego działania, na przykład zapisania zmiany priorytetu pacjenta do bazy danych albo odświeżenia widoku kolejki po stronie użytkownika. Porównanie momentu rozpoczęcia i zakończenia operacji pozwala obliczyć opóźnienie, a analiza wielu takich pomiarów umożliwia ocenę wydajności całego systemu lub jego poszczególnych komponentów.

W naszym programie tuż po wejściu do endpointu zapisywany jest czas startu. Następnie wykonywana jest logika endpointu - między t0 a końcem pomiaru działają operacje backendowe, m.in.:

-próba przyjęcia pacjenta z kolejki,
-usunięcie pacjenta z patients.db,
-aktualizacje stanu.

Koniec pomiaru i obliczenie latencji.

### 4.2 API latencja avg


Średni czas obsługi żądania API (w ms), liczony z ostatnich próbek.


### 4.3 API jitter

Istotnym uzupełnieniem pomiaru latencji jest pomiar jitteru, czyli zmienności opóźnienia pomiędzy kolejnymi wykonaniami tej samej lub podobnej operacji. Jitter pokazuje, na ile stabilny czasowo jest system: nawet jeśli średnia latencja pozostaje akceptowalna, duże wahania pomiędzy kolejnymi pomiarami mogą świadczyć o niestabilności działania, przeciążeniu lub problemach ze współbieżnością. Dzięki instrumentacji możliwe jest więc nie tylko określenie średniego czasu odpowiedzi, ale także ocena, czy system działa w sposób przewidywalny i powtarzalny.

---

## 5. Omówienie zagadnień współbieżności (race condition)

### 5.1 Czym jest współbieżność

Współbieżność oznacza wykonywanie wielu operacji „w tym samym czasie” (np. przez wiele wątków lub wielu użytkowników systemu).  
W aplikacjach webowych oznacza to, że serwer może obsługiwać kilka żądań jednocześnie, które odwołują się do tych samych danych.

### 5.2 Czym jest race condition

Race condition (wyścig) występuje wtedy, gdy wynik końcowy zależy od kolejności wykonania równoległych operacji na wspólnym zasobie.  
Jeżeli nie ma poprawnej synchronizacji, dwa żądania mogą odczytać ten sam stan „przed zmianą” i zapisać kolidujące wyniki.

### 5.3 Jak race condition wygląda w naszym projekcie

W projekcie występują dwa główne miejsca podatne na wyścig:

1. **Przyjęcie pacjenta**  
   Dwóch operatorów może równocześnie próbować przyjąć tego samego pierwszego pacjenta z kolejki.

2. **Zmiana priorytetu**  
   Dwóch operatorów może jednocześnie zmieniać priorytet tego samego pacjenta (np. jeden zwiększa, drugi zmniejsza).

### 5.4 Wymuszenie race condition

Do celów dydaktycznych race condition jest świadomie wzmacniany przez:
- równoległe żądania (test wielowątkowy),
- celowe opóźnienie (`time.sleep(0.5)`) w sekcjach krytycznych przy wyłączonej ochronie.

Dzięki temu łatwo odtworzyć konflikt i obserwować jego skutki w API i metrykach.

### 5.5 Mechanizm blokady / wersjonowania

W projekcie zastosowano dwa podejścia:

- **Blokada (lock)**  
  Przy włączonej ochronie operacje wykonywane są w sekcji krytycznej, co serializuje dostęp do kolejki i ogranicza konflikty.

- **Wykrywanie konfliktu zapisu (wariant wersjonowania logicznego, tryb bez ochrony)**  
  Dla zmiany priorytetu wykorzystywany jest znacznik ostatniego autora (`_last_writer`) oraz porównanie stanu przed/po (`old_priority` vs bieżący `priority`).  
  Jeśli w międzyczasie inny operator zmieni rekord, backend zwraca `"conflict"`, a endpoint mapuje to na HTTP `409`.

### 5.6 Porównanie przed i po poprawce (test)

Do porównania używany jest skrypt `test.py`, który:
- loguje kilku użytkowników,
- uruchamia równoczesne żądania w rundach (`admit` albo `priority`),
- zbiera statusy odpowiedzi (`200`, `409`, `-1`) i podsumowanie.

Interpretacja wyników:
- **Przed poprawką / przy wyłączonej ochronie**: częstsze konflikty i niestabilność wyniku (więcej sytuacji wyścigu).
- **Po poprawce / przy włączonej ochronie**: stabilniejszy, deterministyczny przebieg operacji (mniej konfliktów logicznych).
- Dodatkowo w UI aktualizowane są metryki latencji/jitteru dla `admit` i `priority` oraz licznik `Race condition`, co pozwala obserwować efekt zmian na żywo.
