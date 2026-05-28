import threading # do tworzenia wątków symulujących jednoczesne żądania
import time # do mierzenia czasu i implementacji timeoutów
import random # do losowego wyboru pacjenta w testach priorytetu
import requests # do wykonywania żądań HTTP do API kolejki

# ── Konfiguracja ─────────────────────────────────────────────────────────────

BASE_URL     = "http://localhost:5000"

# Konta użytkowników — każdy wątek używa osobnego konta.

USER_ACCOUNTS = [
    ("admin",  "admin"),
    ("197570", "kti"),
]

TEST_ROUNDS        = 10
TEST_MODE          = "priority"   # "admit" — przyjęcie pacjenta | "priority" — zmiana priorytetu
THREADS_PER_ROUND  = 2 # liczba równoczesnych żądań w każdej rundzie (minimum 2)
PRIORITY_PATIENT_ID = None

# Wymuszanie częstszych RC dla admit:
ROUND_PATIENT_WAIT_TIMEOUT_S = 15.0
MIN_PATIENTS_FOR_ADMIT_ROUND = 1
WAIT_FOR_COOLDOWN_BEFORE_ADMIT_ROUND = True
COOLDOWN_WAIT_TIMEOUT_S = 60.0
# ─────────────────────────────────────────────────────────────────────────────


# Funkcja logowania — zwraca sesję z zalogowanym użytkownikiem
def login(username: str, password: str) -> requests.Session | None:
    session = requests.Session()
    try:
        resp = session.post(
            f"{BASE_URL}/login",
            data={"username": username, "password": password},
            allow_redirects=True,
            timeout=5,
        )
        if resp.status_code == 200 and "logout" in resp.text.lower():
            return session
        print(f"  [BŁĄD] Logowanie nieudane dla '{username}' (status {resp.status_code})")
        return None
    except requests.exceptions.ConnectionError:
        print(f"  [BŁĄD] Nie można połączyć się z {BASE_URL} — czy serwer jest uruchomiony?")
        return None

# Funkcja wysyła dummy(testowe) GET żeby nawiązać połączenie TCP przed testem, co eliminuje różnicę czasu pierwszego żądania(bo pierwszy request może mieć opóźnienie).
def warmup(session: requests.Session):
    try:
        session.get(f"{BASE_URL}/api/queue/state", timeout=5)
    except Exception:
        pass

# Funkcja do przyjęcia pacjenta — zwraca status code odpowiedzi HTTP (200, 409, itp.) lub -1 w przypadku błędu połączenia
def admit_patient(session: requests.Session) -> int:
    try:
        resp = session.post( 
            f"{BASE_URL}/api/queue/admit", # żądanie HTTP GET do API - endpoint do przyjęcia pacjenta
            headers={"Content-Type": "application/json"}, # nagłówek informujący, że dane są w formacie JSON
            timeout=5, # timeout 5 sekund, aby dać szansę na wykrycie sytuacji wyścigu, zamiast szybkiego błędu połączenia
        )
        return resp.status_code
    except Exception as e:
        print(f"  [WYJĄTEK] {e}")
        return -1

# Funkcja do zmiany priorytetu pacjenta — zwraca status code odpowiedzi HTTP (200, 409, itp.) lub -1 w przypadku błędu połączenia
def change_priority(session: requests.Session, patient_id: int, priority: int) -> int:
    try:
        resp = session.post(
            f"{BASE_URL}/api/queue/change-priority", # endpoint do zmiany priorytetu
            json={"patient_id": patient_id, "priority": priority}, # dane JSON z ID pacjenta i nowym priorytetem
            timeout=5, # timeout 5 sekund, aby dać szansę na wykrycie sytuacji wyścigu, zamiast szybkiego błędu połączenia
        )
        return resp.status_code
    except Exception as e:
        print(f"  [WYJĄTEK] {e}")
        return -1

# Funkcja do pobrania listy ID pacjentów aktualnie w kolejce (z API) — zwraca listę ID lub pustą listę w przypadku błędu
def get_patient_ids(session: requests.Session, limit: int | None = None) -> list[int]:
    try:
        resp = session.get(f"{BASE_URL}/api/queue/state", timeout=5) # endpoint do pobrania stanu kolejki, który zawiera listę pacjentów
        data = resp.json()
        patients = data.get("patients", [])
        ids = [p.get("id") for p in patients if p.get("id") is not None] # wyciągnięcie listy ID pacjentów z odpowiedzi API
        return ids[:limit] if isinstance(limit, int) and limit > 0 else ids
    except Exception:
        return []

# Funkcja do oczekiwania na pojawienie się pacjentów w API — zwraca listę ID pacjentów lub pustą listę, jeśli timeout minął
def wait_for_patient_ids(session: requests.Session, min_count: int = 1, timeout_s: float = 10.0) -> list[int]:
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        ids = get_patient_ids(session)
        if len(ids) >= min_count:
            return ids
        time.sleep(0.5)
    return get_patient_ids(session)

# Funkcja do pobrania czasu oczekiwania w kolejce z API — zwraca czas w sekundach lub 0.0 w przypadku błędu
def get_session_wait_time(session: requests.Session) -> float:
    try:
        resp = session.get(f"{BASE_URL}/api/queue/state", timeout=5)
        data = resp.json()
        return float(data.get("wait_time", 0.0) or 0.0)
    except Exception:
        return 0.0

# Funkcja do oczekiwania aż wszystkie sesje będą gotowe do przyjęcia pacjenta (wait_time <= 0) — zwraca True jeśli gotowe, False jeśli timeout minął
def wait_until_sessions_ready_for_admit(
    sessions: list[requests.Session],
    timeout_s: float = 60.0,
) -> bool:
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        waits = [get_session_wait_time(s) for s in sessions]
        if all(w <= 0.0 for w in waits):
            return True
        time.sleep(0.2)
    return False

# Funkcja do uruchomienia jednej rundy testowej — każdy wątek wykonuje jednocześnie żądanie admit lub change-priority, a wyniki (statusy) są zbierane w liście results
def run_round(
    sessions: list,
    mode: str,
    results: list,
    barrier: threading.Barrier,
    target_patient_ids: list[int] | None = None,
):
    statuses = [-1] * len(sessions)
    
    # Każdy wątek czeka na barierze, aż wszyscy będą gotowi, a następnie wykonuje swoje żądanie (admit lub change-priority) i zapisuje status odpowiedzi HTTP w liście statuses.
    def make_task(idx, session):
        def task():
            try:
                # Wszyscy ruszają równocześnie
                barrier.wait(timeout=5)
            except threading.BrokenBarrierError:
                statuses[idx] = -1
                return

            if mode == "admit":
                statuses[idx] = admit_patient(session) # wykonanie żądania admit i zapisanie statusu odpowiedzi
            else:
                if not target_patient_ids:
                    statuses[idx] = -1
                    return
                selected_patient_id = target_patient_ids[idx % len(target_patient_ids)]
                priority = 4 if idx % 2 == 0 else 2
                statuses[idx] = change_priority(session, selected_patient_id, priority)
        return task

    # Tworzenie i uruchamianie wątków dla tej rundy
    threads = [threading.Thread(target=make_task(i, s), daemon=True) for i, s in enumerate(sessions)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    results.append(tuple(statuses)) # zapisanie wyników tej rundy (statusów odpowiedzi) do listy results

# Funkcja do podsumowania wyników testu — zlicza ile rund zakończyło się wszystkimi 200, ile miało przynajmniej jeden 409, i ile miało błędy połączenia (-1), a następnie wypisuje wnioski
def summarize(results: list, label: str):
    print(f"\n{'─' * 50}")
    print(f"  Wyniki: {label}")
    print(f"{'─' * 50}")

    all_ok    = sum(1 for r in results if all(s == 200 for s in r))
    any_409   = sum(1 for r in results if 409 in r)  # race condition
    any_429   = sum(1 for r in results if 429 in r)  # cooldown 2s, NIE race
    any_error = sum(1 for r in results if -1 in r)

    print(f"  Łączna liczba rund:              {len(results)}")
    print(f"  Wszyscy 200:                     {all_ok:>3}")
    print(f"  Przynajmniej jeden 409 (race):   {any_409:>3}")
    print(f"  Przynajmniej jeden 429 (cooldown): {any_429:>3}")
    print(f"{'─' * 50}")

# Funkcja do tworzenia sesji dla podanych kont — zwraca listę sesji lub pustą listę w przypadku błędu
def create_sessions(accounts: list[tuple[str, str]]) -> list[requests.Session]:
    sessions = []
    for i, (login_name, password) in enumerate(accounts, 1):
        print(f"      [{i}] '{login_name}'...")
        sess = login(login_name, password)
        if not sess:
            return []
        warmup(sess)
        sessions.append(sess)
    return sessions

# Główna funkcja testu — loguje użytkowników, przygotowuje sesje, a następnie uruchamia wielokrotne rundy testowe, zbierając i podsumowując wyniki.
def main():
    print("=" * 50)
    print("  Test race condition — System Kolejkowania")
    print("=" * 50)

    if THREADS_PER_ROUND < 2:
        print("  [BŁĄD] THREADS_PER_ROUND musi być >= 2")
        return
    if len(USER_ACCOUNTS) < THREADS_PER_ROUND:
        print(f"  [BŁĄD] Za mało kont w USER_ACCOUNTS (potrzeba >= {THREADS_PER_ROUND})")
        return

    accounts = USER_ACCOUNTS[:THREADS_PER_ROUND]

    print(f"\n[1/4] Logowanie {THREADS_PER_ROUND} użytkowników...")
    sessions = create_sessions(accounts)
    if not sessions:
        return

    print("[2/4] Pre-warm połączeń TCP (eliminuje różnicę czasu pierwszego żądania)...")
    print("      Gotowe.")

    print(f"[3/4] Tryb: {TEST_MODE.upper()}, wątków na rundę: {THREADS_PER_ROUND}, rund: {TEST_ROUNDS}")

    patient_id = PRIORITY_PATIENT_ID
    if TEST_MODE == "priority" and patient_id is not None:
        print(f"      Wymuszone pacjent ID: {patient_id}")

    print(f"[4/4] Uruchamiam {TEST_ROUNDS} rund jednoczesnych żądań...\n")

    results = []
    barrier = threading.Barrier(THREADS_PER_ROUND)

    for i in range(TEST_ROUNDS):
        target_ids = None

        if TEST_MODE == "admit":
            if WAIT_FOR_COOLDOWN_BEFORE_ADMIT_ROUND:
                ready = wait_until_sessions_ready_for_admit(
                    sessions,
                    timeout_s=COOLDOWN_WAIT_TIMEOUT_S,
                )
                if not ready:
                    results.append(tuple([-1] * THREADS_PER_ROUND))
                    print(f"  Runda {i+1:>2}: timeout czekania na cooldown  ✗")
                    continue

            ids = wait_for_patient_ids(
                sessions[0],
                min_count=MIN_PATIENTS_FOR_ADMIT_ROUND,
                timeout_s=ROUND_PATIENT_WAIT_TIMEOUT_S,
            )
            if len(ids) < MIN_PATIENTS_FOR_ADMIT_ROUND:
                results.append(tuple([-1] * THREADS_PER_ROUND))
                print(f"  Runda {i+1:>2}: brak pacjentów w API  ✗")
                continue

        elif TEST_MODE == "priority":
            if patient_id is not None:
                target_ids = [patient_id]
            else:
                ids = wait_for_patient_ids(sessions[0], min_count=1, timeout_s=10.0)
                if not ids:
                    results.append(tuple([-1] * THREADS_PER_ROUND))
                    print(f"  Runda {i+1:>2}: brak pacjentów w API  ✗")
                    continue
                selected_id = random.choice(ids)
                target_ids = [selected_id]

        run_round(
            sessions,
            TEST_MODE,
            results,
            barrier,
            target_patient_ids=target_ids,
        )
        statuses = results[-1]
        has_409 = 409 in statuses
        has_429 = 429 in statuses
        icon = "✗" if has_409 else ("⏳" if has_429 else "✓")
        status_str = "  ".join(f"u{j+1}={s}" for j, s in enumerate(statuses))
        if TEST_MODE == "priority":
            print(f"  Runda {i+1:>2}: {status_str}  target={target_ids[0] if target_ids else None}  {icon}")
        else:
            print(f"  Runda {i+1:>2}: {status_str}  {icon}")

    summarize(results, f"tryb={TEST_MODE}, wątki={THREADS_PER_ROUND}")


if __name__ == "__main__":
    main()