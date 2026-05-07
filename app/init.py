import time
import threading
from flask import Flask, jsonify, redirect, render_template, url_for, request, session
from flask_restful import Resource, Api
from flask.views import MethodView
from app.gen_patient import generate_next_patient_record
from app.priorities import get_service_time_for_priority
from .database import PatientDB
from .login import init_auth


app = Flask(__name__)  # Tworzymy instancję aplikacji Flask
app.config["SECRET_KEY"] = "change-this-secret-key"
api = Api(app)
patient_db = PatientDB()
init_auth(app, patient_db)

# Prosty rejestr pacjentów, który przechowuje listę oczekujących pacjentów oraz aktualnie obsługiwanego pacjenta.
class PatientRegistry:
    def __init__(self):
        self._patients = []
        self._user_states = {}  # user_key -> {"current_patient", "last_admit_time", "current_service_seconds"}
        self._lock = threading.Lock()

    # Metoda do dodawania pacjenta do kolejki. Przyjmuje dane pacjenta i tworzy rekord, który jest dodawany do listy oczekujących pacjentów.
    def add_patient(self, first_name: str, last_name: str, admission_number: int, priority_number: int, arrival_time: float, gender: str) -> bool:
        with self._lock:
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
        """Sortuje pacjentów malejąco po priorytecie (5 = przód, 1 = koniec)"""
        def get_priority(patient):
            # Obsługa zarówno priority jak i priority_number dla kompatybilności
            priority = patient.get("priority") or patient.get("priority_number")
            return priority if priority is not None else 1
        
        self._patients.sort(key=get_priority, reverse=True)

    # Metoda do dodawania pacjenta wygenerowanego przez generator. Przyjmuje gotowy rekord pacjenta i dodaje go do listy oczekujących pacjentów.
    def add_generated_patient(self, patient_record: dict) -> bool:
        with self._lock:
            self._patients.append(patient_record)
            self._sort_patients()
        return True

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
        with self._lock:
            state = self._get_or_create_user_state(user_key)
            cooldown_seconds = max(0, int(state["current_service_seconds"] or 0))
            if current_time - float(state["last_admit_time"] or 0) < cooldown_seconds:
                return False

            if self._patients:
                state["current_patient"] = self._patients.pop(0)
                current_service = state["current_patient"].get("service_time_seconds")
                state["current_service_seconds"] = int(current_service) if isinstance(current_service, (int, float)) else 5
                state["last_admit_time"] = current_time
                return True
            return False
    # Metoda zwracająca aktualnie obsługiwanego pacjenta.
    def get_current_patient(self, user_key: str):
        with self._lock:
            state = self._get_or_create_user_state(user_key)
            return state["current_patient"]

    # Metoda zwracająca listę wszystkich oczekujących pacjentów.
    def all_patients(self):
        with self._lock:
            return list(self._patients)

    def clear(self):
        with self._lock:
            self._patients = []
            self._user_states = {}

    # Metoda do zmiany priorytetu pacjenta w kolejce i przesunięcia go na odpowiednią pozycję
    def change_patient_priority(self, patient_id: int, new_priority: int) -> bool:
        """
        Zmienia priorytet pacjenta w kolejce i sortuje kolejkę na nowo.
        Zwraca True jeśli pacjent został znaleziony i priorytet zmieniony.
        """
        if not 1 <= new_priority <= 5:
            return False
        
        with self._lock:
            patient = None
            for p in self._patients:
                if p.get("id") == patient_id:
                    patient = p
                    break
            
            if patient:
                patient["priority"] = new_priority
                patient["service_time_seconds"] = get_service_time_for_priority(new_priority)
                self._sort_patients()
                return True
        return False

    def get_wait_time(self, user_key: str) -> float:
        with self._lock:
            state = self._get_or_create_user_state(user_key)
            last_admit_time = float(state.get("last_admit_time") or 0.0)
            current_service_seconds = max(0, int(state.get("current_service_seconds") or 0))

            if last_admit_time <= 0:
                return 0.0

            time_passed = time.time() - last_admit_time
            return max(0.0, current_service_seconds - time_passed)

    def get_current_service_seconds(self, user_key: str) -> int:
        with self._lock:
            state = self._get_or_create_user_state(user_key)
            return max(0, int(state.get("current_service_seconds") or 0))

patient_registry = PatientRegistry()

def _restore_registry_from_db():
    for patient in patient_db.get_all_patients():
        patient_registry.add_generated_patient(patient)

_restore_registry_from_db()

_generator_started = False
_generator_start_lock = threading.Lock()

# Funkcja uruchamiająca w tle generator pacjentów. Generuje pacjentów w nieskończoność, dodając ich do rejestru pacjentów z odpowiednimi opóźnieniami między kolejnymi generacjami.
def _patient_generation_worker():
    lam_arrival = 15.0
    lam_service = 10.0
    min_service_seconds = 2

    while True:
        suggested_id = patient_db.get_next_patient_id()
        wait_seconds, patient_record = generate_next_patient_record(
            patient_id=suggested_id,
            lam_arrival=lam_arrival,
            lam_service=lam_service,
            min_service_seconds=min_service_seconds,
        )

        time.sleep(wait_seconds)

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

    with _generator_start_lock:
        if _generator_started:
            return

        worker = threading.Thread(target=_patient_generation_worker, daemon=True)
        worker.start()
        _generator_started = True

def _get_request_user_key() -> str:
    username = session.get("username")
    if isinstance(username, str) and username.strip():
        return username.strip()
    return request.remote_addr or "anonymous"

# Klasa widoku obsługująca główną stronę aplikacji. W metodzie GET uruchamia generator pacjentów (jeśli jeszcze nie został uruchomiony), oblicza czas oczekiwania na przyjęcie kolejnego pacjenta oraz renderuje szablon HTML z aktualną listą pacjentów, aktualnie obsługiwanem pacjentem i czasem oczekiwania.
class PatientFormView(MethodView):
    def get(self):
        start_background_patient_generation()
        user_key = _get_request_user_key()
        patients = patient_db.get_all_patients()
        wait_time = patient_registry.get_wait_time(user_key)
        current_service_seconds = patient_registry.get_current_service_seconds(user_key)

        return render_template(
            "index.html",
            patients=patients,
            current=patient_registry.get_current_patient(user_key),
            wait_time=round(wait_time, 1),
            current_service_seconds=current_service_seconds,
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
    }

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
    admitted = patient_registry.admit_patient(user_key)
    if admitted:
        current = patient_registry.get_current_patient(user_key)
        if isinstance(current, dict) and current.get("id") is not None:
            patient_db.delete_patient(int(current["id"]))
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
    data = request.get_json()
    patient_id = data.get("patient_id")
    new_priority = data.get("priority")

    if patient_id is None or new_priority is None:
        return jsonify({"success": False, "error": "Missing patient_id or priority"}), 400

    try:
        patient_id = int(patient_id)
        new_priority = int(new_priority)
    except (ValueError, TypeError):
        return jsonify({"success": False, "error": "Invalid patient_id or priority"}), 400

    success = patient_registry.change_patient_priority(patient_id, new_priority)

    if success:
        updated = next((p for p in patient_registry.all_patients() if p.get("id") == patient_id), None)
        if isinstance(updated, dict):
            updated = dict(updated)
            updated["priority"] = new_priority
            updated["priority_number"] = new_priority
            updated["service_time_seconds"] = get_service_time_for_priority(new_priority)
            patient_db.add_patient(updated)

    state = _build_queue_state(_get_request_user_key())
    state["success"] = success
    return jsonify(state)
