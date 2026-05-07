(() => {
	// Pobieranie elementów DOM i danych z atrybutów
	const body = document.body;
	const btn = document.getElementById("admitBtn");
	const barContainer = document.getElementById("cooldown-container");
	const progressBar = document.getElementById("progress-bar");
	const admitForm = document.getElementById("admitForm");
	const currentNameEl = document.getElementById("current-name");
	const currentMetaEl = document.getElementById("current-meta");
	const currentEmptyEl = document.getElementById("current-empty");
	const queueCountEl = document.getElementById("queue-count");
	const queueBodyEl = document.getElementById("queue-body");
	const queueOverflowEl = document.getElementById("queue-overflow");

	// Inicjalizacja czasu oczekiwania i całkowitego czasu obsługi z atrybutów danych
	let waitTime = Number(body?.dataset?.waitTime ?? "0") || 0;
	let totalTime = Number(body?.dataset?.currentServiceSeconds ?? "0") || 0;
	let cooldownInterval = null;

	// Funkcja do odliczania aktualizacji interfejsu - progress bar
	function startCooldown() {
		if (!btn || !barContainer || !progressBar) {
			return;
		}

		if (cooldownInterval) {
			clearInterval(cooldownInterval);
			cooldownInterval = null;
		}

		if (waitTime > 0 && totalTime > 0) {
			btn.disabled = true;
			btn.style.background = "#ccc";
			btn.style.cursor = "not-allowed";
			barContainer.style.display = "block";

			cooldownInterval = setInterval(() => {
				waitTime -= 0.1;
				const percentage = Math.max(0, (waitTime / totalTime) * 100);
				progressBar.style.width = `${percentage}%`;

				if (waitTime <= 0) {
					clearInterval(cooldownInterval);
					cooldownInterval = null;
					btn.disabled = false;
					btn.style.background = "#28a745";
					btn.style.cursor = "pointer";
					barContainer.style.display = "none";
				}
			}, 100);
		} else {
			btn.disabled = false;
			btn.style.background = "#28a745";
			btn.style.cursor = "pointer";
			barContainer.style.display = "none";
		}
	}

	// Funkcja do generowania aktualnie obsługiwanego pacjenta
	function renderCurrent(currentPatient) {
		if (!currentNameEl || !currentMetaEl || !currentEmptyEl) {
			return;
		}

		if (currentPatient) {
			currentNameEl.style.display = "block";
			currentMetaEl.style.display = "block";
			currentEmptyEl.style.display = "none";

			const fullName = currentPatient.full_name || `${currentPatient.first_name || ""} ${currentPatient.last_name || ""}`.trim();
			currentNameEl.innerHTML = `<strong>${fullName || "-"}</strong>`;
			currentMetaEl.textContent = `ID: ${currentPatient.id ?? "-"} | Płeć: ${currentPatient.gender ?? "-"} | Przybycie: ${currentPatient.arrival_time ?? "-"} | Czas przyjęcia: ${currentPatient.service_time_seconds ?? "-"} s | Priorytet: ${currentPatient.priority ?? "-"}`;
		} else {
			currentNameEl.style.display = "none";
			currentMetaEl.style.display = "none";
			currentEmptyEl.style.display = "block";
			currentEmptyEl.textContent = "Gabinet wolny - naciśnij przycisk poniżej.";
		}
	}

	// Funkcja do generowania listy pacjentów w kolejce
	function renderQueue(state) {
		if (queueCountEl) {
			queueCountEl.textContent = `Łącznie w kolejce: ${state.count ?? 0}`;
		}

		if (!queueBodyEl) {
			return;
		}

		const rows = (state.patients_preview || [])
			.map((patient) => {
				const fullName = patient.full_name || `${patient.first_name || ""} ${patient.last_name || ""}`.trim();
				const priorityText = ["Niebieski", "Zielony", "Żółty", "Pomarańczowy", "Czerwony"][patient.priority - 1] || "-";
				return `
					<tr>
						<td style="border: 1px solid #ddd; padding: 8px;">${patient.id ?? "-"}</td>
						<td style="border: 1px solid #ddd; padding: 8px;">${patient.gender ?? "-"}</td>
						<td style="border: 1px solid #ddd; padding: 8px;">${fullName || "-"}</td>
						<td style="border: 1px solid #ddd; padding: 8px;">${patient.arrival_time ?? "-"}</td>
						<td style="border: 1px solid #ddd; padding: 8px;">
							<select class="priority-select patient-priority-select" data-patient-id="${patient.id ?? ""}" style="width: 100%; padding: 4px; border: 1px solid #ddd; border-radius: 3px;">
								<option value="1" ${patient.priority === 1 ? 'selected' : ''}>1 - Niebieski</option>
								<option value="2" ${patient.priority === 2 ? 'selected' : ''}>2 - Zielony</option>
								<option value="3" ${patient.priority === 3 ? 'selected' : ''}>3 - Żółty</option>
								<option value="4" ${patient.priority === 4 ? 'selected' : ''}>4 - Pomarańczowy</option>
			// Dodaj obsługę zmiany priorytetu dla wszystkich selektorów
			const prioritySelects = queueBodyEl.querySelectorAll(".patient-priority-select");
			prioritySelects.forEach(select => {
				select.addEventListener("change", handlePriorityChange);
			});
		} else {
			queueBodyEl.innerHTML = '<tr><td colspan="6
						</td>
						<td style="border: 1px solid #ddd; padding: 8px;">${patient.service_time_seconds ?? "-"} s</td>
					</tr>
				`;
			})
			.join("");

		if (rows) {
			queueBodyEl.obsługi zmiany priorytetu pacjenta
	async function handlePriorityChange(event) {
		const select = event.target;
		const patientId = select.getAttribute("data-patient-id");
		const newPriority = select.value;

		try {
			const response = await fetch("/api/queue/change-priority", {
				method: "POST",
				headers: { "Content-Type": "application/json" },
				body: JSON.stringify({
					patient_id: parseInt(patientId),
					priority: parseInt(newPriority)
				})
			});

			if (response.ok) {
				const state = await response.json();
				applyState(state);
			} else {
				alert("Błąd przy zmianie priorytetu pacjenta.");
				location.reload();
			}
		} catch (error) {
			console.error("Błąd:", error);
			alert("Nie udało się zmienić priorytetu.");
		}
	}

	// Funkcja do innerHTML = rows;
		} else {
			queueBodyEl.innerHTML = '<tr><td colspan="4" style="border: 1px solid #ddd; padding: 8px; color: #666;">Brak osób w kolejce.</td></tr>';
		}

		if (queueOverflowEl) {
			if ((state.overflow_count || 0) > 0) {
				queueOverflowEl.style.display = "block";
				queueOverflowEl.textContent = `... oraz ${state.overflow_count} osób oczekujących dalej.`;
			} else {
				queueOverflowEl.style.display = "none";
				queueOverflowEl.textContent = "";
			}
		}
	}

	// Funkcja do zastosowania stanu kolejki i aktualizacji interfejsu
	function applyState(state) {
		renderCurrent(state.current || null);
		renderQueue(state);

		waitTime = Number(state.wait_time ?? 0) || 0;
		totalTime = Number(state.current_service_seconds ?? 0) || 0;
		startCooldown();
	}

	// Funkcja do obsługi przyjęcia następnego pacjenta
	function setupAdmitForm() {
		if (!admitForm || !btn) {
			return;
		}

		admitForm.addEventListener("submit", async (event) => {
			event.preventDefault();
			btn.disabled = true;
			btn.innerHTML = "Przetwarzanie...";

			try {
				const response = await fetch("/api/queue/admit", {
					method: "POST",
					headers: { "Content-Type": "application/json" },
				});
				if (response.ok) {
					const state = await response.json();
					applyState(state);
				}
			} catch (error) {
			} finally {
				btn.innerHTML = "PRZYJMIJ NASTĘPNEGO";
			}
		});
	}

	// Funkcja do okresowego odświeżania stanu kolejki
	async function refreshQueueState() {
		try {
			const response = await fetch("/api/queue/state", { cache: "no-store" });
			if (!response.ok) {
				return;
			}

			const state = await response.json();
			applyState(state);
		} catch (error) {
		}
	}

	// Funkcja resetująca kolejkę przez API
	async function resetQueue() {
		const response = await fetch("/api/queue/reset", { method: "POST" });
		if (!response.ok) {
			alert("Nie udało się wyzerować kolejki.");
			return;
		}
		window.location.reload();
	}

	startCooldown();
	setupAdmitForm();

	document.addEventListener("DOMContentLoaded", () => {
		const resetBtn = document.getElementById("resetQueueBtn");
		if (resetBtn) {
			resetBtn.style.position = "fixed";
			resetBtn.style.top = "16px";
			resetBtn.style.right = "16px";
			resetBtn.style.zIndex = "1000";
			resetBtn.addEventListener("click", resetQueue);
		}
	});

	refreshQueueState();
	setInterval(refreshQueueState, 1000);
})();
