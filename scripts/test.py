"""
Skrypt testowy do porównania działania aplikacji z włączoną i wyłączoną
ochroną przed race condition.

Symuluje użytkowników logujących się na osobnych kontach i jednocześnie
wykonujących operacje przyjęcia pacjenta lub zmiany priorytetu.

Konfiguracja:
    - Ustaw USER_ACCOUNTS — lista (login, hasło) dla każdego wątku
    - Ustaw BASE_URL jeśli serwer działa na innym porcie
    - Ustaw TEST_ROUNDS — ile razy powtórzyć test
    - Ustaw TEST_MODE: "admit" lub "priority"
    - Ustaw THREADS_PER_ROUND — ile wątków uderza jednocześnie (min. 2)
      Więcej wątków = większa szansa kolizji (np. 4-5 niemal gwarantuje race condition)
"""

import threading
import requests

# ── Konfiguracja ─────────────────────────────────────────────────────────────

BASE_URL     = "http://localhost:5000"

# Konta użytkowników — każdy wątek używa osobnego konta.
# Liczba wpisów musi być >= THREADS_PER_ROUND.
USER_ACCOUNTS = [
    ("admin",  "admin"),
    ("197570", "kti"),
    ("admin",  "admin"),   # można powtórzyć konto jeśli brak 3. użytkownika
    ("197570", "kti"),
]

TEST_ROUNDS        = 20
TEST_MODE          = "admit"   # "admit" — przyjęcie pacjenta | "priority" — zmiana priorytetu
THREADS_PER_ROUND  = 2         # ile wątków uderza jednocześnie; zwiększ do 3-5 dla pewniejszej kolizji
PRIORITY_PATIENT_ID = None     # wypełniane automatycznie przy trybie "priority"

# ─────────────────────────────────────────────────────────────────────────────


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


def warmup(session: requests.Session):
    """Wysyła dummy GET żeby nawiązać połączenie TCP przed testem."""
    try:
        session.get(f"{BASE_URL}/api/queue/state", timeout=5)
    except Exception:
        pass


def admit_patient(session: requests.Session) -> int:
    try:
        resp = session.post(
            f"{BASE_URL}/api/queue/admit",
            headers={"Content-Type": "application/json"},
            timeout=10,
        )
        return resp.status_code
    except Exception as e:
        print(f"  [WYJĄTEK] {e}")
        return -1


def change_priority(session: requests.Session, patient_id: int, priority: int) -> int:
    try:
        resp = session.post(
            f"{BASE_URL}/api/queue/change-priority",
            json={"patient_id": patient_id, "priority": priority},
            timeout=10,
        )
        return resp.status_code
    except Exception as e:
        print(f"  [WYJĄTEK] {e}")
        return -1


def get_first_patient_id(session: requests.Session) -> int | None:
    try:
        resp = session.get(f"{BASE_URL}/api/queue/state", timeout=5)
        data = resp.json()
        patients = data.get("patients", [])
        if patients:
            return patients[0].get("id")
    except Exception:
        pass
    return None


def run_round(
    sessions: list,
    mode: str,
    patient_id: int | None,
    results: list,
    barrier: threading.Barrier,
):
    statuses = [-1] * len(sessions)

    def make_task(idx, session):
        def task():
            # Wszyscy czekają razem — ruszają dokładnie w tym samym momencie
            barrier.wait()
            if mode == "admit":
                statuses[idx] = admit_patient(session)
            else:
                # Naprzemiennie priorytety 4 i 2 żeby kolizja była widoczna
                priority = 4 if idx % 2 == 0 else 2
                statuses[idx] = change_priority(session, patient_id, priority)
        return task

    threads = [threading.Thread(target=make_task(i, s)) for i, s in enumerate(sessions)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    results.append(tuple(statuses))


def summarize(results: list, label: str):
    print(f"\n{'─' * 50}")
    print(f"  Wyniki: {label}")
    print(f"{'─' * 50}")

    all_ok    = sum(1 for r in results if all(s == 200 for s in r))
    any_409   = sum(1 for r in results if 409 in r)
    any_error = sum(1 for r in results if -1 in r)

    print(f"  Łączna liczba rund:              {len(results)}")
    print(f"  Wszyscy 200 (race condition):    {all_ok:>3}  ← wyścig niezauważony")
    print(f"  Przynajmniej jeden 409:          {any_409:>3}  ← wykryty wyścig")
    print(f"  Błędy połączenia:                {any_error:>3}")
    print(f"{'─' * 50}")

    if any_409 == 0 and all_ok > 0:
        print("  WNIOSEK: Brak wykrytych konfliktów — możliwy race condition!")
    elif any_409 == len(results):
        print("  WNIOSEK: Każda runda wykryła konflikt — ochrona działa poprawnie.")
    else:
        print(f"  WNIOSEK: Konflikty wykryto w {any_409}/{len(results)} rundach.")


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
    sessions = []
    for i, (login_name, password) in enumerate(accounts, 1):
        print(f"      [{i}] '{login_name}'...")
        sess = login(login_name, password)
        if not sess:
            return
        sessions.append(sess)

    print("[2/4] Pre-warm połączeń TCP (eliminuje różnicę czasu pierwszego żądania)...")
    for sess in sessions:
        warmup(sess)
    print("      Gotowe.")

    print(f"[3/4] Tryb: {TEST_MODE.upper()}, wątków na rundę: {THREADS_PER_ROUND}, rund: {TEST_ROUNDS}")

    patient_id = PRIORITY_PATIENT_ID
    if TEST_MODE == "priority" and patient_id is None:
        print("      Pobieram ID pierwszego pacjenta z kolejki...")
        patient_id = get_first_patient_id(sessions[0])
        if patient_id is None:
            print("  [BŁĄD] Brak pacjentów w kolejce. Uruchom serwer i poczekaj na pacjentów.")
            return
        print(f"      Wybrany pacjent ID: {patient_id}")

    print(f"[4/4] Uruchamiam {TEST_ROUNDS} rund jednoczesnych żądań...\n")

    results = []
    # Barrier(n+1): n wątków roboczych + główny wątek (żeby sam też poczekał przed każdą rundą)
    barrier = threading.Barrier(THREADS_PER_ROUND + 1)

    for i in range(TEST_ROUNDS):
        run_round(sessions, TEST_MODE, patient_id, results, barrier)
        # Główny wątek też czeka na barierze — zwalnia wszystkich jednocześnie
        barrier.wait()
        statuses = results[-1]
        has_409 = 409 in statuses
        icon = "✗" if has_409 else "✓"
        status_str = "  ".join(f"u{j+1}={s}" for j, s in enumerate(statuses))
        print(f"  Runda {i+1:>2}: {status_str}  {icon}")
        # Brak sleep między rundami — okno 0.5s na serwerze jest wystarczające

    summarize(results, f"tryb={TEST_MODE}, wątki={THREADS_PER_ROUND}")


if __name__ == "__main__":
    main()
