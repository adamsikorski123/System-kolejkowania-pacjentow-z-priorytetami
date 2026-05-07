import random
from datetime import datetime

from scripts.simulate_patients import poisson_patient_generator
from app.nazwy import IMIONA_MESKIE, IMIONA_ZENSKIE, NAZWISKA_MESKIE, NAZWISKA_ZENSKIE
from app.priorities import get_service_time_for_priority

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

# Funkcja do generowania priorytetu pacjenta według rozkładu Poissona (lambda=2.5 dla średniej priorytetu ~3)
def generate_patient_priority(lam_priority=2.5):
	"""
	Generuje priorytet pacjenta (1-5) na podstawie rozkładu Poissona
	lam_priority: parametr lambda rozkładu Poissona
	"""
	import numpy as np
	priority = np.random.poisson(lam_priority) + 1  # +1 aby mieć zakresy od 1 do 5+
	return min(max(int(priority), 1), 5)  # Ograniczenie do zakresu 1-5

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
	priority = generate_patient_priority()
	service_time_seconds = get_service_time_for_priority(priority)

	patient_record = {
		"id": patient_id,
		"gender": gender,
		"first_name": first_name,
		"last_name": last_name,
		"full_name": f"{first_name} {last_name}",
		"arrival_time": datetime.now().strftime("%H:%M:%S"),
		"priority": priority,
		"service_time_seconds": service_time_seconds,
	}

	return wait_seconds, patient_record
