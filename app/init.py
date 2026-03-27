from flask import Flask, jsonify, redirect, render_template, request, url_for
from flask_restful import Resource, Api
from flask.views import MethodView

app = Flask(__name__)
api = Api(app)


class PatientRegistry:
    """Simple in-memory registry for submitted full names."""

    def __init__(self):
        self._patients = []

    def add_patient(self, first_name: str, last_name: str) -> bool:
        first_name = first_name.strip()
        last_name = last_name.strip()

        if not first_name or not last_name:
            return False

        self._patients.append(
            {
                "first_name": first_name,
                "last_name": last_name,
                "full_name": f"{first_name} {last_name}",
            }
        )
        return True

    def all_patients(self):
        return list(self._patients)


patient_registry = PatientRegistry()


class PatientFormView(MethodView):
    def get(self):
        return render_template("index.html", patients=patient_registry.all_patients(), error=None)

    def post(self):
        first_name = request.form.get("first_name", "")
        last_name = request.form.get("last_name", "")

        if not patient_registry.add_patient(first_name, last_name):
            return render_template(
                "index.html",
                patients=patient_registry.all_patients(),
                error="Wpisz imię i nazwisko.",
            )

        return redirect(url_for("patient_form"))


app.add_url_rule('/', view_func=PatientFormView.as_view('patient_form'), methods=['GET', 'POST'])
