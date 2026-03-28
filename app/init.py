import time
import threading
from flask import Flask, jsonify, redirect, render_template, url_for
from flask_restful import Resource, Api
from flask.views import MethodView

from app.gen_patient import generate_next_patient_record

app = Flask(__name__)
api = Api(app)


class PatientRegistry:
    """Simple in-memory registry for submitted full names."""

    def __init__(self):
        self._patients = []
        self._current_patient = None
        self._last_admit_time = 0
        self._current_service_seconds = 0
        self._lock = threading.Lock()

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

    def add_generated_patient(self, patient_record: dict) -> bool:
        with self._lock:
            self._patients.append(patient_record)
        return True

    def admit_patient(self):
        """Przenosi pierwszego pacjenta z kolejki do pola 'current_patient'."""
        current_time = time.time()
        cooldown_seconds = max(0, int(self._current_service_seconds or 0))
        if current_time - self._last_admit_time < cooldown_seconds:
            return False # Za wcześnie!

        with self._lock:
            if self._patients:
                self._current_patient = self._patients.pop(0)
                current_service = self._current_patient.get("service_time_seconds")
                self._current_service_seconds = int(current_service) if isinstance(current_service, (int, float)) else 5
                self._last_admit_time = current_time # Aktualizujemy czas
                return True
            return False

    def get_current_patient(self):
        with self._lock:
            return self._current_patient

    def all_patients(self):
        with self._lock:
            return list(self._patients)

patient_registry = PatientRegistry()


_generator_started = False
_generator_start_lock = threading.Lock()


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


def start_background_patient_generation():
    global _generator_started

    with _generator_start_lock:
        if _generator_started:
            return

        worker = threading.Thread(target=_patient_generation_worker, daemon=True)
        worker.start()
        _generator_started = True

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


@app.route('/api/queue/state', methods=['GET'])
def queue_state():
    return jsonify(_build_queue_state())


@app.route('/api/queue/admit', methods=['POST'])
def queue_admit():
    admitted = patient_registry.admit_patient()
    state = _build_queue_state()
    state["admitted"] = admitted
    return jsonify(state)

@app.route('/admit', methods=['POST'])
def admit_patient():
    patient_registry.admit_patient() # Wywołujemy metodę, która istnieje
    return redirect(url_for('patient_form'))
