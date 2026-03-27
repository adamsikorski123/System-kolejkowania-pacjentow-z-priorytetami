import time
from flask import Flask, jsonify, redirect, render_template, request, url_for
from flask_restful import Resource, Api
from flask.views import MethodView

app = Flask(__name__)
api = Api(app)


class PatientRegistry:
    """Simple in-memory registry for submitted full names."""

    def __init__(self):
        self._patients = []
        self._current_patient = None
        self._last_admit_time = 0

    def add_patient(self, first_name: str, last_name: str, admission_number: int, priority_number: int, arrival_time: float, gender: str) -> bool:
        
        self._patients.append({
            "full_name": f"{first_name} {last_name}",
            "admission_number": admission_number,

        })
        return True

    def admit_patient(self):
        """Przenosi pierwszego pacjenta z kolejki do pola 'current_patient'."""
        current_time = time.time()
        if current_time - self._last_admit_time < 5:
            return False # Za wcześnie!
        
        if self._patients:
            self._current_patient = self._patients.pop(0)
            self._last_admit_time = current_time # Aktualizujemy czas
            return True
        return False

    def get_current_patient(self):
        return self._current_patient

    def all_patients(self):
        return list(self._patients)

patient_registry = PatientRegistry()
#działaj

class PatientFormView(MethodView):
    def get(self):
#dsadsad
        current_time = time.time()
        time_passed = current_time - patient_registry._last_admit_time
        wait_time = max(0, 5 - time_passed) if patient_registry._last_admit_time > 0 else 0
 
        return render_template(
            "index.html", 
            patients=patient_registry.all_patients(), 
            current=patient_registry.get_current_patient(), 
            wait_time=round(wait_time, 1),
            error=None
        )
#proba
    def post(self):
        first_name = request.form.get("first_name", "")
        last_name = request.form.get("last_name", "")
        # Proste nadawanie numeru na podstawie wielkości listy
        num = len(patient_registry.all_patients()) + (1 if patient_registry.get_current_patient() else 0) + 1
        patient_registry.add_patient(first_name, last_name, num, 1, time.time(), "unknown")
        return redirect(url_for("patient_form"))
app.add_url_rule('/', view_func=PatientFormView.as_view('patient_form'), methods=['GET', 'POST'])

@app.route('/admit', methods=['POST'])
def admit_patient():
    patient_registry.admit_patient() # Wywołujemy metodę, która istnieje
    return redirect(url_for('patient_form'))




##dara 
