import time
import threading
from flask import Flask, jsonify, redirect, render_template, url_for
from flask_restful import Resource, Api
from flask.views import MethodView
from app.gen_patient import generate_next_patient_record

app = Flask(__name__)  # Tworzymy instancję aplikacji Flask
api = Api(app) # Inicjalizujemy Flask-RESTful API, ale nie definiujemy jeszcze żadnych zasobów.

# Prosty rejestr pacjentów, który przechowuje listę oczekujących pacjentów oraz aktualnie obsługiwanego pacjenta.
class PatientRegistry:

    def __init__(self): # Inicjalizujemy rejestr pacjentów
        self._patients = []
        self._current_patient = None
        self._last_admit_time = 0
        self._current_service_seconds = 0
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
                "priority_number": priority_number,
                "arrival_time": time.strftime("%H:%M:%S", time.localtime(arrival_time)),
                "service_time_seconds": None,
            })
        return True

    # Metoda do dodawania pacjenta wygenerowanego przez generator. Przyjmuje gotowy rekord pacjenta i dodaje go do listy oczekujących pacjentów.
    def add_generated_patient(self, patient_record: dict) -> bool:
        with self._lock:
            self._patients.append(patient_record)
        return True

    # Metoda przenosząca pierwszego pacjenta z kolejki do pola 'current_patient'. Sprawdza, czy minął odpowiedni czas od ostatniego przyjęcia pacjenta (na podstawie czasu obsługi aktualnego pacjenta) i jeśli tak, to przenosi pierwszego pacjenta z listy oczekujących do pola 'current_patient' oraz aktualizuje czas ostatniego przyjęcia.
    def admit_patient(self):
        current_time = time.time()
        cooldown_seconds = max(0, int(self._current_service_seconds or 0))
        if current_time - self._last_admit_time < cooldown_seconds:
            return False

        with self._lock:
            if self._patients:
                self._current_patient = self._patients.pop(0)
                current_service = self._current_patient.get("service_time_seconds")
                self._current_service_seconds = int(current_service) if isinstance(current_service, (int, float)) else 5
                self._last_admit_time = current_time 
                return True
            return False
    # Metoda zwracająca aktualnie obsługiwanego pacjenta.
    def get_current_patient(self):
        with self._lock:
            return self._current_patient

    # Metoda zwracająca listę wszystkich oczekujących pacjentów.
    def all_patients(self):
        with self._lock:
            return list(self._patients)

patient_registry = PatientRegistry()


_generator_started = False
_generator_start_lock = threading.Lock()

# Funkcja uruchamiająca w tle generator pacjentów. Generuje pacjentów w nieskończoność, dodając ich do rejestru pacjentów z odpowiednimi opóźnieniami między kolejnymi generacjami.
def _patient_generation_worker():
    next_patient_id = 1
    lam_arrival = 15.0
    lam_service = 10.0
    min_service_seconds = 2

    while True:
        wait_seconds, patient_record = generate_next_patient_record(
            patient_id=next_patient_id,
            lam_arrival=lam_arrival,
            lam_service=lam_service,
            min_service_seconds=min_service_seconds,
        )

        time.sleep(wait_seconds)
        patient_registry.add_generated_patient(patient_record)
        next_patient_id += 1

# Funkcja sprawdzająca, czy generator już został uruchomiony, a jeśli nie, to uruchamia go w osobnym wątku.
def start_background_patient_generation():
    global _generator_started

    with _generator_start_lock:
        if _generator_started:
            return

        worker = threading.Thread(target=_patient_generation_worker, daemon=True)
        worker.start()
        _generator_started = True

# Klasa widoku obsługująca główną stronę aplikacji. W metodzie GET uruchamia generator pacjentów (jeśli jeszcze nie został uruchomiony), oblicza czas oczekiwania na przyjęcie kolejnego pacjenta oraz renderuje szablon HTML z aktualną listą pacjentów, aktualnie obsługiwanym pacjentem i czasem oczekiwania.
class PatientFormView(MethodView):
    def get(self):
        start_background_patient_generation()
        current_time = time.time()
        time_passed = current_time - patient_registry._last_admit_time
        current_service_seconds = max(0, int(patient_registry._current_service_seconds or 0))
        wait_time = max(0, current_service_seconds - time_passed) if patient_registry._last_admit_time > 0 else 0
 
        return render_template(
            "index.html", 
            patients=patient_registry.all_patients(), 
            current=patient_registry.get_current_patient(), 
            wait_time=round(wait_time, 1),
            current_service_seconds=current_service_seconds,
            error=None
        )


app.add_url_rule('/', view_func=PatientFormView.as_view('patient_form'), methods=['GET'])

# Funkcja pomocnicza do budowania stanu kolejki, która oblicza czas oczekiwania na przyjęcie kolejnego pacjenta, pobiera listę wszystkich oczekujących pacjentów oraz aktualnie obsługiwanego pacjenta, a następnie zwraca te informacje w formie tabeli.
def _build_queue_state():
    current_time = time.time()
    time_passed = current_time - patient_registry._last_admit_time
    current_service_seconds = max(0, int(patient_registry._current_service_seconds or 0))
    wait_time = max(0, current_service_seconds - time_passed) if patient_registry._last_admit_time > 0 else 0

    patients = patient_registry.all_patients()
    current = patient_registry.get_current_patient()

    last_id = patients[-1].get("id", 0) if patients else 0
    current_id = current.get("id", 0) if isinstance(current, dict) else 0

    return {
        "count": len(patients),
        "last_id": last_id,
        "current_id": current_id,
        "current": current,
        "patients_preview": patients[:3],
        "overflow_count": max(0, len(patients) - 3),
        "wait_time": round(wait_time, 1),
        "current_service_seconds": current_service_seconds,
    }

# Endpoint API zwracający podstawowe informacje o stanie kolejki, takie jak liczba oczekujących pacjentów, ID ostatniego pacjenta w kolejce oraz ID aktualnie obsługiwanego pacjenta.
@app.route('/api/queue/version', methods=['GET'])
def queue_version():
    state = _build_queue_state()
    return jsonify(
        {
            "count": state["count"],
            "last_id": state["last_id"],
            "current_id": state["current_id"],
        }
    )

# Endpoint API zwracający pełny stan kolejki, w tym listę oczekujących pacjentów, aktualnie obsługiwanego pacjenta, czas oczekiwania na przyjęcie kolejnego pacjenta oraz czas obsługi aktualnego pacjenta.
@app.route('/api/queue/state', methods=['GET'])
def queue_state():
    return jsonify(_build_queue_state())

# Endpoint API zwracający informację o tym, czy udało się przyjąć kolejnego pacjenta oraz aktualny stan kolejki po tej operacji.
@app.route('/api/queue/admit', methods=['POST'])
def queue_admit():
    admitted = patient_registry.admit_patient()
    state = _build_queue_state()
    state["admitted"] = admitted
    return jsonify(state)

# Endpoint API do ręcznego przyjęcia pacjenta. Wywołuje metodę admit_patient() z rejestru pacjentów
@app.route('/admit', methods=['POST'])
def admit_patient():
    patient_registry.admit_patient()
    return redirect(url_for('patient_form'))
