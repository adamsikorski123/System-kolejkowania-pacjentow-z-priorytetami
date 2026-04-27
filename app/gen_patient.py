import random
from datetime import datetime

from scripts.simulate_patients import poisson_patient_generator
from app.nazwy import IMIONA_MESKIE, IMIONA_ZENSKIE, NAZWISKA_MESKIE, NAZWISKA_ZENSKIE

# Prosty generator pacjentów, który losuje płeć i dobiera zgodne imię + nazwisko.
def generate_patient_identity():
	gender = random.choice(["M", "K"])
	if gender == "M":
		first_name = random.choice(IMIONA_MESKIE)
		last_name = random.choice(NAZWISKA_MESKIE)
	else:
		first_name = random.choice(IMIONA_ZENSKIE)
		last_name = random.choice(NAZWISKA_ZENSKIE)

	return gender, first_name, last_name

# Funkcja pomocnicza do generowania kolejnego pacjenta i obliczania czasu oczekiwania do jego pojawienia się.
def generate_next_patient_record(patient_id, lam_arrival, lam_service, min_service_seconds):

	next_patient = next( 
		poisson_patient_generator(
			lam_arrival=lam_arrival,
			lam_service=lam_service,
			t_end=10_000.0,
			min_service_seconds=min_service_seconds,
		)
	)

	gender, first_name, last_name = generate_patient_identity()
	wait_seconds = next_patient.arrival_time * 60.0

	patient_record = {
		"id": patient_id,
		"gender": gender,
		"first_name": first_name,
		"last_name": last_name,
		"full_name": f"{first_name} {last_name}",
		"arrival_time": datetime.now().strftime("%H:%M:%S"),
		"service_time_seconds": int(round(next_patient.service_time * 60.0)),
	}

	return wait_seconds, patient_record
