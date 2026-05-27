import time # Używane do zarządzania czasem, np. do obliczania czasu oczekiwania i czasu obsługi pacjentów
import threading # Używane do synchronizacji dostępu do wspólnych zasobów (np. listy pacjentów) oraz do uruchamiania generatora pacjentów w osobnym wątku
import os # Używane do zarządzania ścieżkami do plików bazy danych
from flask import Flask, jsonify, redirect, render_template, url_for, request, session # Używane do obsługi żądań HTTP, zarządzania sesjami i renderowania szablonów HTML
from flask_restful import Resource, Api # Używane do tworzenia API RESTful
from flask.views import MethodView # Używane do tworzenia klas widoków obsługujących żądania HTTP
from app.gen_patient import generate_next_patient_record # Używane do generowania losowych rekordów pacjentów
from app.priorities import get_service_time_for_priority # Używane do określania czasu obsługi pacjenta na podstawie jego priorytetu
from .database import PatientDB # Używane do zarządzania bazą danych pacjentów i użytkowników
from .login import init_auth # Używane do inicjalizacji mechanizmu uwierzytelniania użytkowników
from .latencja import LatencyJitterMeter # Używane do pomiaru i raportowania metryk związanych z opóźnieniami API i czasem oczekiwania w kolejce
from uuid import uuid4 # Używane do generowania unikalnych kluczy sesji dla operatorów


app = Flask(__name__)  # Tworzymy instancję aplikacji Flask
app.config["SECRET_KEY"] = "change-this-secret-key" # Ustawiamy klucz tajny dla Flask, który jest używany do zarządzania sesjami i innymi funkcjami bezpieczeństwa (należy zmienić na coś unikalnego i bezpiecznego w produkcji)
api = Api(app)

_BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_PATIENTS_DB_PATH = os.path.join(_BASE_DIR, "patients.db")
_USERS_DB_PATH = os.path.join(_BASE_DIR, "users.db")

patient_db = PatientDB(db_name=_PATIENTS_DB_PATH, auth_db_name=_USERS_DB_PATH)
init_auth(app, patient_db) # Inicjalizujemy mechanizm uwierzytelniania użytkowników, przekazując aplikację Flask i bazę danych pacjentów (która zawiera również informacje o użytkownikach)
latency_meter = LatencyJitterMeter() # Tworzymy instancję miernika opóźnień i jittera

# Prosty rejestr pacjentów, który przechowuje listę oczekujących pacjentów oraz aktualnie obsługiwanego pacjenta.
class PatientRegistry:
    def __init__(self):
        self._patients = []
        self._user_states = {}
        self._lock = threading.Lock() # Używamy blokady do synchronizacji dostępu do listy pacjentów i stanu użytkowników, aby uniknąć problemów z równoczesnym dostępem z różnych wątków (np. głównego wątku obsługującego żądania HTTP i wątku generatora pacjentów)

    # Metoda do dodawania pacjenta do kolejki. Przyjmuje dane pacjenta i tworzy rekord, który jest dodawany do listy oczekujących pacjentów.
    def add_patient(self, first_name: str, last_name: str, admission_number: int, priority_number: int, arrival_time: float, gender: str) -> bool:
        #with self._lock:
        self._patients.append({
            "id": admission_number,
            "gender": gender,
            "first_name": first_name,
            "last_name": last_name,
            "full_name": f"{first_name} {last_name}",
            "admission_number": admission_number,
            "priority": priority_number,
            "arrival_time": time.strftime("%H:%M:%S", time.localtime(arrival_time)),
            "service_time_seconds": None,
        })
        self._sort_patients()
        return True

    # Metoda do sortowania pacjentów po priorytecie (wyższy priorytet = przód)
    def _sort_patients(self):
        def get_priority(patient):
            # Obsługa zarówno priority jak i priority_number dla kompatybilności
            priority = patient.get("priority") or patient.get("priority_number")
            return priority if priority is not None else 1
        
        self._patients.sort(key=get_priority, reverse=True)

    # Metoda do dodawania pacjenta wygenerowanego przez generator. Przyjmuje gotowy rekord pacjenta i dodaje go do listy oczekujących pacjentów.
    def add_generated_patient(self, patient_record: dict) -> bool:
        #with self._lock:
        patient_record = dict(patient_record)
        patient_record.setdefault("arrival_epoch", time.time())
        self._patients.append(patient_record)
        self._sort_patients()
        return True

    # Metoda pomocnicza do pobierania lub tworzenia stanu użytkownika na podstawie unikalnego klucza. Stan użytkownika zawiera informacje o aktualnie obsługiwanym pacjencie, czasie ostatniego przyjęcia pacjenta oraz czasie obsługi aktualnego pacjenta.
    def _get_or_create_user_state(self, user_key: str):
        state = self._user_states.get(user_key)
        if state is None:
            state = {
                "current_patient": None,
                "last_admit_time": 0.0,
                "current_service_seconds": 0,
            }
            self._user_states[user_key] = state
        return state

    # Metoda przenosząca pierwszego pacjenta z kolejki do pola 'current_patient'. Sprawdza, czy minął odpowiedni czas od ostatniego przyjęcia pacjenta (na podstawie czasu obsługi aktualnego pacjenta) i jeśli tak, to przenosi pierwszego pacjenta z listy oczekujących do pola 'current_patient' oraz aktualizuje czas ostatniego przyjęcia.
    def admit_patient(self, user_key: str):
        current_time = time.time()

        with _race_protection_lock:
            protection = _race_protection_enabled

        if protection:
            with self._lock:
                state = self._get_or_create_user_state(user_key)
                cooldown_seconds = max(0, int(state["current_service_seconds"] or 0))
                if current_time - float(state["last_admit_time"] or 0) < cooldown_seconds:
                    return False
                if self._patients:
                    patient = self._patients.pop(0)
                    state["current_patient"] = patient
                    current_service = patient.get("service_time_seconds")
                    state["current_service_seconds"] = int(current_service) if isinstance(current_service, (int, float)) else 5
                    state["last_admit_time"] = current_time
                    return True
                return False
        else:
            #with self._lock:
            state = self._get_or_create_user_state(user_key)
            cooldown_seconds = max(0, int(state["current_service_seconds"] or 0))
            if current_time - float(state["last_admit_time"] or 0) < cooldown_seconds:
                return False
            if self._patients:
                patient = self._patients[0]   # odczyt bez usuwania — obaj wątki widzą tego samego pacjenta
                time.sleep(0.5)               # celowe opóźnienie do demonstracji race condition
                try:
                    self._patients.remove(patient)
                except ValueError:
                    return "conflict"         # pacjent już przyjęty przez innego operatora
                state["current_patient"] = patient
                current_service = patient.get("service_time_seconds")
                state["current_service_seconds"] = int(current_service) if isinstance(current_service, (int, float)) else 5
                state["last_admit_time"] = current_time
                return True
            return False
        
    # Metoda zwracająca aktualnie obsługiwanego pacjenta.
    def get_current_patient(self, user_key: str):
        #with self._lock:
        state = self._get_or_create_user_state(user_key)
        return state["current_patient"]

    # Metoda zwracająca listę wszystkich oczekujących pacjentów.
    def all_patients(self):
        #with self._lock:
        return list(self._patients)

    # Metoda do czyszczenia rejestru pacjentów i stanu użytkowników (przydatna do testów lub resetowania stanu aplikacji).
    def clear(self):
        #with self._lock:
        self._patients = []
        self._user_states = {}

    #!!!! WSPÓŁBIEŻNOŚĆ
    # Metoda do zmiany priorytetu pacjenta w kolejce i przesunięcia go na odpowiednią pozycję
    def change_patient_priority(self, patient_id: int, new_priority: int, user_key: str = "") -> bool:
        if not 1 <= new_priority <= 5:
            return False

        with _race_protection_lock:
            protection = _race_protection_enabled

        if protection:
            with self._lock:
                patient = None
                for p in self._patients:
                    if p.get("id") == patient_id:
                        patient = p
                        break
                if patient:
                    patient["priority"] = new_priority
                    patient["_last_writer"] = user_key
                    patient["service_time_seconds"] = get_service_time_for_priority(new_priority)
                    self._sort_patients()
                    return True
            return False
        else:
                #with self._lock:
            patient = None
            for p in self._patients:
                if p.get("id") == patient_id:
                    patient = p
                    break

            if patient:
                old_priority = patient["priority"]
                time.sleep(0.5)  # celowe opóźnienie do demonstracji race condition
                changed_by_other = (
                    patient["priority"] != old_priority and
                    patient.get("_last_writer") != user_key
                )
                if changed_by_other:
                    return "conflict"
                patient["priority"] = new_priority
                patient["_last_writer"] = user_key
                patient["service_time_seconds"] = get_service_time_for_priority(new_priority)
                self._sort_patients()
                return True

            return False

    # Metoda do obliczania czasu oczekiwania na przyjęcie kolejnego pacjenta. Oblicza czas, który pozostał do momentu, gdy będzie można przyjąć kolejnego pacjenta, na podstawie czasu ostatniego przyjęcia i czasu obsługi aktualnego pacjenta.
    def get_wait_time(self, user_key: str) -> float:
        #with self._lock:
        state = self._get_or_create_user_state(user_key)
        last_admit_time = float(state.get("last_admit_time") or 0.0)
        current_service_seconds = max(0, int(state.get("current_service_seconds") or 0))

        if last_admit_time <= 0:
            return 0.0

        time_passed = time.time() - last_admit_time
        return max(0.0, current_service_seconds - time_passed)

    # Metoda do pobierania czasu obsługi aktualnego pacjenta. Zwraca czas obsługi aktualnie obsługiwanego pacjenta, który jest przechowywany w stanie użytkownika.
    def get_current_service_seconds(self, user_key: str) -> int:
        #with self._lock:
        state = self._get_or_create_user_state(user_key)
        return max(0, int(state.get("current_service_seconds") or 0))

patient_registry = PatientRegistry()

# Przy starcie aplikacji ładujemy pacjentów z bazy danych do rejestru pacjentów, aby mieć aktualną listę oczekujących pacjentów i ich dane.
def _restore_registry_from_db():
    for patient in patient_db.get_all_patients():
        patient_registry.add_generated_patient(patient)

_restore_registry_from_db()

_generator_started = False # Flaga informująca, czy generator pacjentów został już uruchomiony, aby uniknąć wielokrotnego uruchamiania generatora w przypadku wielu żądań do głównej strony aplikacji.
_generator_start_lock = threading.Lock() # Blokada do synchronizacji dostępu do flagi _generator_started, aby uniknąć problemów z równoczesnym dostępem z różnych wątków (np. głównego wątku obsługującego żądania HTTP i wątku generatora pacjentów)

_generation_paused = False
_generation_pause_lock = threading.Lock()

_race_protection_enabled = False
_race_protection_lock = threading.Lock()

# Funkcja uruchamiająca w tle generator pacjentów. Generuje pacjentów w nieskończoność, dodając ich do rejestru pacjentów z odpowiednimi opóźnieniami między kolejnymi generacjami.
def _patient_generation_worker():
    lam_arrival = 15.0
    lam_service = 10.0
    min_service_seconds = 2

    while True:
        with _generation_pause_lock:
            paused = _generation_paused

        if paused:
            time.sleep(1)
            continue

        suggested_id = patient_db.get_next_patient_id()
        wait_seconds, patient_record = generate_next_patient_record(
            patient_id=suggested_id,
            lam_arrival=lam_arrival,
            lam_service=lam_service,
            min_service_seconds=min_service_seconds,
        )

        time.sleep(wait_seconds)

        with _generation_pause_lock:
            paused = _generation_paused

        if paused:
            continue

        # ID ustalane przy zapisie -> po resecie zaczyna znowu od 1
        next_id = patient_db.get_next_patient_id()
        patient_record["id"] = next_id
        if "admission_number" in patient_record:
            patient_record["admission_number"] = next_id

        patient_registry.add_generated_patient(patient_record)
        patient_db.add_patient(patient_record)

# Funkcja sprawdzająca, czy generator już został uruchomiony, a jeśli nie, to uruchamia go w osobnym wątku.
def start_background_patient_generation():
    global _generator_started

    #with _generator_start_lock: # Blokada do synchronizacji dostępu do flagi _generator_started, aby uniknąć problemów z równoczesnym dostępem z różnych wątków (np. głównego wątku obsługującego żądania HTTP i wątku generatora pacjentów)
    if _generator_started:
        return

    worker = threading.Thread(target=_patient_generation_worker, daemon=True) # Tworzymy wątek, który będzie uruchamiał funkcję _patient_generation_worker. Ustawiamy go jako daemon, aby zakończył się automatycznie po zamknięciu aplikacji.
    worker.start()
    _generator_started = True

# Funkcja pomocnicza do generowania unikalnego klucza dla operatora na podstawie nazwy użytkownika (jeśli jest dostępna) i unikalnego klucza sesji. Ten klucz jest używany do przechowywania stanu użytkownika w rejestrze pacjentów, aby mieć oddzielny stan dla każdego operatora (np. aktualnie obsługiwany pacjent, czas ostatniego przyjęcia pacjenta itp.).
def _get_request_user_key() -> str:
    session_key = session.get("_operator_session_key")
    if not session_key:
        session_key = uuid4().hex
        session["_operator_session_key"] = session_key

    username = session.get("username")
    if isinstance(username, str) and username.strip():
        return f"{username.strip()}:{session_key}"

    return f"anonymous:{session_key}"

# Klasa widoku obsługująca główną stronę aplikacji. W metodzie GET uruchamia generator pacjentów (jeśli jeszcze nie został uruchomiony), oblicza czas oczekiwania na przyjęcie kolejnego pacjenta oraz renderuje szablon HTML z aktualną listą pacjentów, aktualnie obsługiwanem pacjentem i czasem oczekiwania.
class PatientFormView(MethodView):
    # Metoda obsługująca żądania GET do głównej strony aplikacji. Uruchamia generator pacjentów (jeśli jeszcze nie został uruchomiony), pobiera aktualną listę pacjentów, oblicza czas oczekiwania na przyjęcie kolejnego pacjenta oraz renderuje szablon HTML z tymi informacjami.
    def get(self):
        start_background_patient_generation()
        user_key = _get_request_user_key()
        patients = patient_db.get_all_patients()
        wait_time = patient_registry.get_wait_time(user_key)
        current_service_seconds = patient_registry.get_current_service_seconds(user_key)
        metrics = latency_meter.snapshot()

        # Renderujemy szablon HTML "index.html", przekazując do niego listę pacjentów, aktualnie obsługiwanego pacjenta, czas oczekiwania na przyjęcie kolejnego pacjenta, czas obsługi aktualnego pacjenta oraz metryki opóźnień API i czasu oczekiwania w kolejce. Szablon HTML będzie odpowiedzialny za wyświetlenie tych informacji w czytelny sposób dla operatora.
        return render_template(
            "index.html",
            patients=patients,
            current=patient_registry.get_current_patient(user_key),
            wait_time=round(wait_time, 1),
            current_service_seconds=current_service_seconds,
            metrics=metrics,
            error=None
        )


app.add_url_rule('/', view_func=PatientFormView.as_view('patient_form'), methods=['GET'])

# Funkcja pomocnicza do budowania stanu kolejki, która oblicza czas oczekiwania na przyjęcie kolejnego pacjenta, pobiera listę wszystkich oczekujących pacjentów oraz aktualnie obsługiwanego pacjenta, a następnie zwraca te informacje w formie tabeli.
def _build_queue_state(user_key: str):
    patients = [_normalize_patient(p) for p in patient_registry.all_patients()]
    current = _normalize_patient(patient_registry.get_current_patient(user_key))
    wait_time = patient_registry.get_wait_time(user_key)
    current_service_seconds = patient_registry.get_current_service_seconds(user_key)

    last_id = patients[-1].get("id", 0) if patients else 0
    current_id = current.get("id", 0) if isinstance(current, dict) else 0

    metrics = latency_meter.snapshot()
    with _generation_pause_lock:
        paused = _generation_paused
    with _race_protection_lock:
        protection = _race_protection_enabled
    return {
        "count": len(patients),
        "last_id": last_id,
        "current_id": current_id,
        "current": current,
        "patients": patients,
        "patients_preview": patients[:3],
        "overflow_count": max(0, len(patients) - 3),
        "wait_time": round(wait_time, 1),
        "current_service_seconds": current_service_seconds,
        "api_latency_last_ms": metrics["api_latency_last_ms"],
        "api_latency_avg_ms": metrics["api_latency_avg_ms"],
        "api_latency_jitter_ms": metrics["api_latency_jitter_ms"],

        "admit_latency_last_ms": metrics["admit_latency_last_ms"],
        "admit_latency_avg_ms": metrics["admit_latency_avg_ms"],
        "admit_latency_jitter_ms": metrics["admit_latency_jitter_ms"],

        "prio_latency_last_ms": metrics["prio_latency_last_ms"],
        "prio_latency_avg_ms": metrics["prio_latency_avg_ms"],
        "prio_latency_jitter_ms": metrics["prio_latency_jitter_ms"],

        "queue_wait_last_s": metrics["queue_wait_last_s"],
        "queue_wait_avg_s": metrics["queue_wait_avg_s"],
        "queue_wait_jitter_s": metrics["queue_wait_jitter_s"],
        "race_condition_count": metrics["race_condition_count"],
        "generation_paused": paused,
        "race_protection_enabled": protection,
    }

# Funkcja pomocnicza do normalizacji danych pacjenta, która zapewnia, że dane pacjenta mają spójny format, np. konwertuje priorytet na liczbę całkowitą i zapewnia, że jest w odpowiednim zakresie (1-5). Ta funkcja jest używana przed zwróceniem danych pacjenta w API, aby mieć pewność, że dane są spójne i łatwe do obsługi po stronie klienta.
def _normalize_patient(patient):
    if not isinstance(patient, dict):
        return patient

    normalized = dict(patient)
    raw_priority = normalized.get("priority", normalized.get("priority_number", 1))

    try:
        priority = int(raw_priority)
    except (TypeError, ValueError):
        priority = 1

    priority = max(1, min(5, priority))
    normalized["priority"] = priority
    normalized["priority_number"] = priority
    return normalized

# Endpoint API zwracający podstawowe informacje o stanie kolejki, takie jak liczba oczekujących pacjentów, ID ostatniego pacjenta w kolejce oraz ID aktualnie obsługiwanego pacjenta.
@app.route('/api/queue/version', methods=['GET'])
def queue_version():
    user_key = _get_request_user_key()
    state = _build_queue_state(user_key)
    return jsonify({
        "count": state["count"],
        "last_id": state["last_id"],
        "current_id": state["current_id"],
    })

# Endpoint API zwracający pełny stan kolejki, w tym listę oczekujących pacjentów, aktualnie obsługiwanego pacjenta, czas oczekiwania na przyjęcie kolejnego pacjenta oraz czas obsługi aktualnego pacjenta.
@app.route('/api/queue/state', methods=['GET'])
def queue_state():
    user_key = _get_request_user_key()
    return jsonify(_build_queue_state(user_key))

# Endpoint API zwracający informację o tym, czy udało się przyjąć kolejnego pacjenta oraz aktualny stan kolejki po tej operacji.
@app.route('/api/queue/admit', methods=['POST'])
def queue_admit():
    user_key = _get_request_user_key()
    t0 = time.perf_counter()
    admitted = patient_registry.admit_patient(user_key)

    if admitted == "conflict":
        latency_meter.record_race_condition()
        api_latency_ms = (time.perf_counter() - t0) * 1000.0
        latency_meter.record_admit_api_latency_ms(api_latency_ms)
        return jsonify({
            "success": False,
            "conflict": True,
            "race_condition_count": latency_meter.snapshot()["race_condition_count"],
        }), 409

    if admitted:
        current = patient_registry.get_current_patient(user_key)
        if isinstance(current, dict):
            try:
                queue_wait_s = max(0.0, time.time() - float(current.get("arrival_epoch", time.time())))
            except (TypeError, ValueError):
                queue_wait_s = 0.0
            latency_meter.record_queue_wait_s(queue_wait_s) # Rejestrujemy czas oczekiwania pacjenta w kolejce jako metrykę, aby mieć informacje o tym, jak długo pacjenci czekają na przyjęcie do obsługi.

            if current.get("id") is not None:
                patient_db.delete_patient(int(current["id"]))

    api_latency_ms = (time.perf_counter() - t0) * 1000.0
    latency_meter.record_admit_api_latency_ms(api_latency_ms)

    state = _build_queue_state(user_key)
    state["admitted"] = admitted
    return jsonify(state)

# Endpoint API do ręcznego przyjęcia pacjenta. Wywołuje metodę admit_patient() z rejestru pacjentów
@app.route('/admit', methods=['POST'])
def admit_patient():
    user_key = _get_request_user_key()
    admitted = patient_registry.admit_patient(user_key)
    if admitted:
        current = patient_registry.get_current_patient(user_key)
        if isinstance(current, dict) and current.get("id") is not None:
            patient_db.delete_patient(int(current["id"]))
    return redirect(url_for('patient_form'))

# Endpoint API resetujący kolejkę.
@app.route('/api/queue/reset', methods=['POST'])
def queue_reset():
    patient_registry.clear()
    patient_db.clear_all_patients()
    state = _build_queue_state(_get_request_user_key())
    state["reset"] = True
    return jsonify(state)

# Endpoint API do zmiany priorytetu pacjenta w kolejce
@app.route('/api/queue/change-priority', methods=['POST'])
def change_priority():
    t0 = time.perf_counter()

    def _respond(payload, status=200):
        api_latency_ms = (time.perf_counter() - t0) * 1000.0
        latency_meter.record_prio_api_latency_ms(api_latency_ms)
        return jsonify(payload), status

    data = request.get_json()
    patient_id = data.get("patient_id")
    new_priority = data.get("priority")

    if patient_id is None or new_priority is None:
        return _respond({"success": False, "error": "Missing patient_id or priority"}, 400)

    try:
        patient_id = int(patient_id)
        new_priority = int(new_priority)
    except (ValueError, TypeError):
        return _respond({"success": False, "error": "Invalid patient_id or priority"}, 400)

    result = patient_registry.change_patient_priority(patient_id, new_priority, _get_request_user_key())

    if result == "conflict":
        latency_meter.record_race_condition()
        return _respond({
            "success": False,
            "conflict": True,
            "race_condition_count": latency_meter.snapshot()["race_condition_count"],
        }, 409)

    if result:
        updated = next((p for p in patient_registry.all_patients() if p.get("id") == patient_id), None)
        if isinstance(updated, dict):
            updated = dict(updated)
            updated["priority"] = new_priority
            updated["priority_number"] = new_priority
            updated["service_time_seconds"] = get_service_time_for_priority(new_priority)
            patient_db.add_patient(updated)

    state = _build_queue_state(_get_request_user_key())
    state["success"] = bool(result)
    return _respond(state)

# Endpoint API przełączający stan generowania pacjentów (wstrzymaj/wznów).
@app.route('/api/queue/generation/toggle', methods=['POST'])
def toggle_generation():
    global _generation_paused
    with _generation_pause_lock:
        _generation_paused = not _generation_paused
        paused = _generation_paused
    return jsonify({"generation_paused": paused})

# Endpoint API przełączający ochronę przed race condition (włącz/wyłącz).
@app.route('/api/queue/protection/toggle', methods=['POST'])
def toggle_protection():
    global _race_protection_enabled
    with _race_protection_lock:
        _race_protection_enabled = not _race_protection_enabled
        enabled = _race_protection_enabled
    return jsonify({"race_protection_enabled": enabled})

# Endpoint API zwracający metryki związane z opóźnieniami API i czasem oczekiwania w kolejce, takie jak ostatnie, średnie i jitter dla obu tych metryk.
@app.route('/api/metrics/latency', methods=['GET'])
def latency_metrics():
    return jsonify(latency_meter.snapshot())
