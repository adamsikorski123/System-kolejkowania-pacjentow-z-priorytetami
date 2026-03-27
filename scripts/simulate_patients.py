from dataclasses import dataclass

import numpy as np

@dataclass
class SyntheticPatient:
    id: int
    arrival_time: float   # np. minuty od t=0
    service_time: float   # czas obsługi (np. w minutach)


def poisson_patient_generator(
    lam_arrival: float,
    lam_service: float,
    t_end: float,
    min_service_seconds: int = 0,
):
    """
    lam_arrival – λ dla przybyć (pacjenci / jednostkę czasu)
    lam_service – λ dla czasu obsługi (średni czas obsługi = 1/lam_service)
    t_end       – horyzont symulacji
    """
    if lam_arrival <= 0:
        raise ValueError("lam_arrival musi być > 0")
    if lam_service <= 0:
        raise ValueError("lam_service musi być > 0")
    if t_end < 0:
        raise ValueError("t_end musi być >= 0")
    if min_service_seconds < 0:
        raise ValueError("min_service_seconds musi być >= 0")

    current_time = 0.0
    patient_id = 1
    min_service_minutes = min_service_seconds / 60.0

    while True:
        current_time += float(np.random.exponential(scale=1.0 / lam_arrival))
        if current_time > t_end:
            break

        # shifted exponential: zachowuje losowość i dodaje dolne ograniczenie
        service_time = min_service_minutes + float(np.random.exponential(scale=1.0 / lam_service))
        yield SyntheticPatient(id=patient_id, arrival_time=current_time, service_time=service_time)
        patient_id += 1
