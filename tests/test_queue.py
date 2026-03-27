import os
import random
import sys
import time
from collections import deque
from datetime import datetime, timedelta
from pathlib import Path


# Pozwala uruchamiać plik bezpośrednio: python tests/test_queue.py
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
	sys.path.insert(0, str(PROJECT_ROOT))

from scripts.simulate_patients import poisson_patient_generator
from tests.nazwy import IMIONA_MESKIE, IMIONA_ZENSKIE, NAZWISKA_MESKIE, NAZWISKA_ZENSKIE


def clear_terminal():
	os.system("cls" if os.name == "nt" else "clear")


def print_queue_table(queue):
	print("Aktualna tablica pacjentów")
	print("=" * 100)
	print(f"{'ID':<6}{'Płeć':<8}{'Imię':<16}{'Nazwisko':<18}{'Arrival time':<28}{'Service [s]':<12}")
	print("-" * 100)

	for patient in queue:
		print(
			f"{patient['id']:<6}{patient['gender']:<8}{patient['first_name']:<16}"
			f"{patient['last_name']:<18}{patient['arrival_time']:<28}{patient['service_time_seconds']:<12}"
		)

	print("=" * 100)
	print(f"Liczba pacjentów: {len(queue)}")


def generate_patient_identity():
	"""Losuje płeć i dobiera zgodne imię + nazwisko."""
	gender = random.choice(["M", "K"])
	if gender == "M":
		first_name = random.choice(IMIONA_MESKIE)
		last_name = random.choice(NAZWISKA_MESKIE)
	else:
		first_name = random.choice(IMIONA_ZENSKIE)
		last_name = random.choice(NAZWISKA_ZENSKIE)

	return gender, first_name, last_name


def print_queue_stats(elapsed_seconds, target_rate_per_minute, total_generated):
	elapsed_minutes = elapsed_seconds / 60.0
	observed_rate = (total_generated / elapsed_minutes) if elapsed_minutes > 0 else 0.0
	print(f"Czas symulacji: {elapsed_seconds:6.1f} s")
	print(f"Docelowe tempo: {target_rate_per_minute:.2f} pacjentów/min")
	print(f"Zaobserwowane tempo: {observed_rate:.2f} pacjentów/min")



def simulate_queue_fill(
	lam_arrival,
	lam_service,
	t_end,
	refresh_seconds,
	min_service_seconds,
):
	"""
	Buduje tablicę pacjentów z generatora Poissona i wyświetla ją stopniowo
	w terminalu, aby było widać jak się zapełnia.
	"""
	queue = []
	base_wall_time = datetime.now()

	for patient in poisson_patient_generator(
		lam_arrival=lam_arrival,
		lam_service=lam_service,
		t_end=t_end,
		min_service_seconds=min_service_seconds,
	):
		gender, first_name, last_name = generate_patient_identity()
		arrival_wall_time = base_wall_time + timedelta(minutes=patient.arrival_time)
		queue.append(
			{
				"id": patient.id,
				"gender": gender,
				"first_name": first_name,
				"last_name": last_name,
				"arrival_time": arrival_wall_time.strftime("%H:%M:%S"),
				"service_time_seconds": int(round(patient.service_time * 60.0)),
			}
		)

		clear_terminal()
		print_queue_table(queue)
		time.sleep(refresh_seconds)

	print("\nSymulacja zakończona.")


def simulate_queue_realtime(
	lam_arrival,
	lam_service,
	max_queue_size,
	min_service_seconds,
	max_runtime_seconds=None,
):
	"""
	Symulacja czasu rzeczywistego (non-stop):
	- terminal odświeża się tylko, gdy pojawi się nowy pacjent,
	- pacjenci dodawani zgodnie z rozkładem z `poisson_patient_generator`,
	- średnie tempo napływu ~ `lam_arrival` pacjentów/min,
	- bufor kolejki ma limit `max_queue_size`, więc nie ma przepełnienia.

	Działa bez końca aż do Ctrl+C.
	`max_runtime_seconds` służy tylko do krótkich testów automatycznych.
	"""
	if lam_arrival <= 0 or lam_service <= 0:
		raise ValueError("lam_arrival i lam_service muszą być > 0")
	if max_queue_size <= 0:
		raise ValueError("max_queue_size musi być > 0")
	if min_service_seconds < 0:
		raise ValueError("min_service_seconds musi być >= 0")

	queue = deque(maxlen=max_queue_size)
	next_patient_id = 1
	total_generated = 0
	dropped = 0
	start_time = time.monotonic()

	try:
		while True:
			now = time.monotonic()
			elapsed_seconds = now - start_time

			if max_runtime_seconds is not None and elapsed_seconds >= max_runtime_seconds:
				break

			# Wylosuj czas do kolejnego pacjenta i jego service_time.
			next_patient = next(
				poisson_patient_generator(
				lam_arrival=lam_arrival,
				lam_service=lam_service,
				t_end=10_000.0,
				min_service_seconds=min_service_seconds,
				)
			)
			wait_seconds = next_patient.arrival_time * 60.0

			if max_runtime_seconds is not None and elapsed_seconds + wait_seconds >= max_runtime_seconds:
				time.sleep(max(0.0, max_runtime_seconds - elapsed_seconds))
				break

			time.sleep(wait_seconds)
			arrival_elapsed_seconds = time.monotonic() - start_time
			gender, first_name, last_name = generate_patient_identity()

			patient_record = {
				"id": next_patient_id,
				"gender": gender,
				"first_name": first_name,
				"last_name": last_name,
				"arrival_time": datetime.now().strftime("%H:%M:%S"),
				"service_time_seconds": int(round(next_patient.service_time * 60.0)),
			}
			if len(queue) == queue.maxlen:
				dropped += 1
			queue.append(patient_record)
			total_generated += 1
			next_patient_id += 1

			clear_terminal()
			print_queue_table(queue)
			print_queue_stats(
				elapsed_seconds=arrival_elapsed_seconds,
				target_rate_per_minute=lam_arrival,
				total_generated=total_generated,
			)
	except KeyboardInterrupt:
		print("\nPrzerwano symulację (Ctrl+C).")

	print("\nSymulacja realtime zakończona.")


if __name__ == "__main__":
	simulate_queue_realtime(
		lam_arrival=15.0,
		lam_service=10.0,
		max_queue_size=100,
		min_service_seconds=2,
	)
