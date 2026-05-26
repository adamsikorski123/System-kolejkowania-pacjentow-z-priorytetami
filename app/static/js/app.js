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
	const apiLatencyAvgEl = document.getElementById("metric-api-latency-avg");
	const apiLatencyJitterEl = document.getElementById("metric-api-latency-jitter");
	const queueWaitAvgEl = document.getElementById("metric-queue-wait-avg");
	const queueWaitJitterEl = document.getElementById("metric-queue-wait-jitter");
	const apiLatencyLastEl = document.getElementById("metric-api-latency-last");
	const queueWaitLastEl = document.getElementById("metric-queue-wait-last");
	const toggleGenerationBtn = document.getElementById("toggleGenerationBtn");
	const toggleProtectionBtn = document.getElementById("toggleProtectionBtn");
	let raceConditionCountEl = document.getElementById("metric-race-condition-count");

	// Inicjalizacja czasu oczekiwania i całkowitego czasu obsługi z atrybutów danych
	let waitTime = Number(body?.dataset?.waitTime ?? "0") || 0;
	let totalTime = Number(body?.dataset?.currentServiceSeconds ?? "0") || 0;
	let cooldownInterval = null;
	let raceConditionCount = 0;

	function getMetricsTableElement() {
		const anchor = apiLatencyAvgEl || apiLatencyJitterEl || queueWaitAvgEl || queueWaitJitterEl || apiLatencyLastEl || queueWaitLastEl;
		if (!anchor) return null;
		return anchor.closest("table") || null;
	}

	function setupMetricsPanelPosition() {
		const table = getMetricsTableElement();
		if (!table) return;

		table.classList.add("metrics-floating");

		// dodatkowe wymuszenie, gdyby layout nadpisywał klasę
		table.style.setProperty("position", "fixed", "important");
		table.style.setProperty("left", "16px", "important");
		table.style.setProperty("bottom", "16px", "important");
		table.style.setProperty("right", "auto", "important");
		table.style.setProperty("top", "auto", "important");
		table.style.setProperty("z-index", "9999", "important");
	}

	function ensureRaceConditionMetricElement() {
		if (raceConditionCountEl) return;

		const anchor = queueWaitLastEl || apiLatencyLastEl || queueWaitAvgEl || apiLatencyAvgEl;
		if (!anchor) return;

		const row = anchor.closest("tr");
		if (row && row.parentElement) {
			const raceRow = document.createElement("tr");
			raceRow.innerHTML = `
				<td style="padding: 6px 8px;">Race condition (409)</td>
				<td id="metric-race-condition-count" style="padding: 6px 8px; font-weight: 600;">0</td>
			`;
			row.parentElement.appendChild(raceRow);
			raceConditionCountEl = raceRow.querySelector("#metric-race-condition-count");
			return;
		}

		const fallback = document.createElement("div");
		fallback.innerHTML = `Race condition (409): <strong id="metric-race-condition-count">0</strong>`;
		(anchor.parentElement || document.body).appendChild(fallback);
		raceConditionCountEl = fallback.querySelector("#metric-race-condition-count");
	}

	function renderRaceConditionCount(value) {
		ensureRaceConditionMetricElement();
		if (raceConditionCountEl) {
			raceConditionCountEl.textContent = `${Math.max(0, Number(value) || 0)}`;
		}
	}

	function syncRaceConditionCount(value) {
		raceConditionCount = Math.max(0, Number(value) || 0);
		renderRaceConditionCount(raceConditionCount);
	}

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

	function getPatientsFromState(state) {
		if (Array.isArray(state?.patients)) return state.patients;
		if (Array.isArray(state?.all_patients)) return state.all_patients;
		if (Array.isArray(state?.queue)) return state.queue;
		if (Array.isArray(state?.patients_preview)) return state.patients_preview;
		return [];
	}

	function validateApiState(state) {
		if (!Array.isArray(state?.patients)) {
			console.warn('API /api/queue/state powinno zwracać pełną listę w polu "patients".');
		}
		return state;
	}

	// Funkcja do generowania listy pacjentów w kolejce
	function renderQueue(state) {
		if (queueCountEl) {
			queueCountEl.textContent = `Łącznie w kolejce: ${state.count ?? 0}`;
		}

		if (!queueBodyEl) {
			return;
		}

		// Preferuj pełną listę; fallback na preview jeśli backend jeszcze jej nie zwraca
		const patients = getPatientsFromState(state);

		const rows = patients
			.map((patient) => {
				const fullName = patient.full_name || `${patient.first_name || ""} ${patient.last_name || ""}`.trim();
				const priority = Math.max(1, Math.min(5, Number(patient.priority ?? 1)));
				return `
					<tr>
						<td style="border: 1px solid #ddd; padding: 8px;">${patient.id ?? "-"}</td>
						<td style="border: 1px solid #ddd; padding: 8px;">${patient.gender ?? "-"}</td>
						<td style="border: 1px solid #ddd; padding: 8px;">${fullName || "-"}</td>
						<td style="border: 1px solid #ddd; padding: 8px;">${patient.arrival_time ?? "-"}</td>
						<td style="border: 1px solid #ddd; padding: 8px;">
							<div style="display:flex; align-items:center; justify-content:center; gap:8px;">
								<button type="button" class="priority-btn priority-minus" data-patient-id="${patient.id ?? ""}" data-priority="${priority}">-</button>
								<span style="min-width: 18px; text-align:center; font-weight:600;">${priority}</span>
								<button type="button" class="priority-btn priority-plus" data-patient-id="${patient.id ?? ""}" data-priority="${priority}">+</button>
							</div>
						</td>
						<td style="border: 1px solid #ddd; padding: 8px;">${patient.service_time_seconds ?? "-"} s</td>
					</tr>
				`;
			})
			.join("");

		if (rows) {
			queueBodyEl.innerHTML = rows;

			const minusButtons = queueBodyEl.querySelectorAll(".priority-minus");
			minusButtons.forEach((btn) => {
				btn.addEventListener("click", () => handlePriorityAdjust(btn, -1));
			});

			const plusButtons = queueBodyEl.querySelectorAll(".priority-plus");
			plusButtons.forEach((btn) => {
				btn.addEventListener("click", () => handlePriorityAdjust(btn, +1));
			});
		} else {
			queueBodyEl.innerHTML = '<tr><td colspan="6" style="border: 1px solid #ddd; padding: 8px; color: #666;">Brak osób w kolejce.</td></tr>';
		}

		// reset starych styli, które psuły kolumny
		queueBodyEl.style.display = "";
		queueBodyEl.style.maxHeight = "";
		queueBodyEl.style.overflowY = "";
		queueBodyEl.style.width = "";
		queueBodyEl.querySelectorAll("tr").forEach((tr) => {
			tr.style.display = "";
			tr.style.width = "";
			tr.style.tableLayout = "";
		});

		const tableEl = queueBodyEl.closest("table");
		ensureQueueTableScroll(tableEl);
	}

	function ensureQueueTableScroll(tableEl) {
		if (!tableEl) return;

		let wrapper = tableEl.parentElement;
		if (!wrapper || !wrapper.classList.contains("queue-table-scroll")) {
			wrapper = document.createElement("div");
			wrapper.className = "queue-table-scroll";
			tableEl.parentNode.insertBefore(wrapper, tableEl);
			wrapper.appendChild(tableEl);
		}

		// ok. 5 wierszy (dopasuj jeśli Twoje wiersze są wyższe/niższe)
		const rowHeight = 48;
		wrapper.style.maxHeight = `${rowHeight * 5}px`;
		wrapper.style.overflowY = "auto";
		wrapper.style.overflowX = "hidden";
		wrapper.style.width = "100%";

		// zachowaj poprawny układ kolumn na pełnej szerokości
		tableEl.style.width = "100%";
		tableEl.style.tableLayout = "fixed";
	}

	async function handlePriorityAdjust(button, delta) {
		const patientId = parseInt(button.getAttribute("data-patient-id"), 10);
		const currentPriority = parseInt(button.getAttribute("data-priority"), 10);
		const nextPriority = Math.max(1, Math.min(5, currentPriority + delta));

		if (!Number.isInteger(patientId) || nextPriority === currentPriority) {
			return;
		}

		await sendPriorityUpdate(patientId, nextPriority);
	}

	async function sendPriorityUpdate(patientId, priority) {
		try {
			const response = await fetch("/api/queue/change-priority", {
				method: "POST",
				headers: { "Content-Type": "application/json" },
				body: JSON.stringify({
					patient_id: patientId,
					priority: priority,
				}),
			});

			if (response.ok) {
				const state = await response.json();
				applyState(state);
			} else if (response.status === 409) {
				const data = await response.json().catch(() => null);
				if (data?.race_condition_count !== undefined) {
					syncRaceConditionCount(data.race_condition_count);
				}
				alert("RACE CONDITION: priorytet został już zmieniony przez innego operatora!");
			} else {
				alert("Błąd przy zmianie priorytetu pacjenta.");
				location.reload();
			}
		} catch (error) {
			console.error("Błąd:", error);
			alert("Nie udało się zmienić priorytetu.");
		}
	}

	// Obsługa zmiany priorytetu pacjenta
	async function handlePriorityChange(event) {
		const select = event.target;
		const patientId = select.getAttribute("data-patient-id");
		const newPriority = select.value;

		try {
			const response = await fetch("/api/queue/change-priority", {
				method: "POST",
				headers: { "Content-Type": "application/json" },
				body: JSON.stringify({
					patient_id: parseInt(patientId, 10),
					priority: parseInt(newPriority, 10),
				}),
			});

			if (response.ok) {
				const state = await response.json();
				applyState(state);
			} else if (response.status === 409) {
				const data = await response.json().catch(() => null);
				if (data?.race_condition_count !== undefined) {
					syncRaceConditionCount(data.race_condition_count);
				}
				alert("Priorytet został już zmieniony przez innego operatora!");
			} else {
				alert("Błąd przy zmianie priorytetu pacjenta.");
				location.reload();
			}
		} catch (error) {
			console.error("Błąd:", error);
			alert("Nie udało się zmienić priorytetu.");
		}
	}

	function renderLatencyMetrics(state) {
		if (apiLatencyAvgEl) apiLatencyAvgEl.textContent = `${Number(state.api_latency_avg_ms ?? 0).toFixed(2)} ms`;
		if (apiLatencyJitterEl) apiLatencyJitterEl.textContent = `${Number(state.api_latency_jitter_ms ?? 0).toFixed(2)} ms`;
		if (queueWaitAvgEl) queueWaitAvgEl.textContent = `${Number(state.queue_wait_avg_s ?? 0).toFixed(2)} s`;
		if (queueWaitJitterEl) queueWaitJitterEl.textContent = `${Number(state.queue_wait_jitter_s ?? 0).toFixed(2)} s`;
		if (apiLatencyLastEl) apiLatencyLastEl.textContent = `${Number(state.api_latency_last_ms ?? 0).toFixed(2)} ms`;
		if (queueWaitLastEl) queueWaitLastEl.textContent = `${Number(state.queue_wait_last_s ?? 0).toFixed(2)} s`;

		if (state && state.race_condition_count !== undefined && state.race_condition_count !== null) {
			syncRaceConditionCount(state.race_condition_count);
		} else {
			renderRaceConditionCount(raceConditionCount);
		}
		setupMetricsPanelPosition();
	}

	// Funkcja do zastosowania stanu kolejki i aktualizacji interfejsu
	function applyState(state) {
		renderCurrent(state.current || null);
		renderQueue(state);
		renderLatencyMetrics(state);
		updateGenerationBtn(state.generation_paused ?? false);
		updateProtectionBtn(state.race_protection_enabled ?? false);

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
				} else if (response.status === 409) {
					const data = await response.json().catch(() => null);
					if (data?.race_condition_count !== undefined) {
						syncRaceConditionCount(data.race_condition_count);
					}
					alert("Pacjent został już przyjęty przez innego operatora!");
				} else {
					alert("Błąd podczas przyjmowania pacjenta.");
				}
			} catch (error) {
				console.error("Błąd przy przyjmowaniu pacjenta:", error);
			} finally {
				btn.innerHTML = "PRZYJMIJ NASTĘPNEGO";
			}
		});
	}

	async function refreshQueueState() {
		try {
			const response = await fetch("/api/queue/state", { cache: "no-store" });
			if (!response.ok) return;

			let state = await response.json();
			state = validateApiState(state);
			applyState(state);
		} catch (error) {
			console.error("Błąd odświeżania kolejki:", error);
		}
	}

	async function resetQueue() {
		const response = await fetch("/api/queue/reset", { method: "POST" });
		if (!response.ok) {
			alert("Nie udało się wyzerować kolejki.");
			return;
		}
		window.location.reload();
	}

	function updateGenerationBtn(paused) {
		if (!toggleGenerationBtn) return;
		if (paused) {
			toggleGenerationBtn.textContent = "WZNÓW GENEROWANIE";
			toggleGenerationBtn.style.background = "#28a745";
		} else {
			toggleGenerationBtn.textContent = "WSTRZYMAJ GENEROWANIE";
			toggleGenerationBtn.style.background = "#e67e00";
		}
	}

	async function toggleGeneration() {
		try {
			const response = await fetch("/api/queue/generation/toggle", { method: "POST" });
			if (response.ok) {
				const data = await response.json();
				updateGenerationBtn(data.generation_paused);
			}
		} catch (error) {
			console.error("Błąd przy przełączaniu generowania:", error);
		}
	}

	function updateProtectionBtn(enabled) {
		if (!toggleProtectionBtn) return;
		if (enabled) {
			toggleProtectionBtn.textContent = "WYŁĄCZ ZABEZPIECZENIA PRZED RACE CONDITION";
			toggleProtectionBtn.style.background = "#28a745";
		} else {
			toggleProtectionBtn.textContent = "WŁĄCZ ZABEZPIECZENIA PRZED RACE CONDITION";
			toggleProtectionBtn.style.background = "#dc3545";
		}
	}

	async function toggleProtection() {
		try {
			const response = await fetch("/api/queue/protection/toggle", { method: "POST" });
			if (response.ok) {
				const data = await response.json();
				updateProtectionBtn(data.race_protection_enabled);
			}
		} catch (error) {
			console.error("Błąd przy przełączaniu ochrony:", error);
		}
	}

	startCooldown();
	setupAdmitForm();
	setupMetricsPanelPosition();
	ensureRaceConditionMetricElement();
	renderRaceConditionCount(raceConditionCount);

	document.addEventListener("DOMContentLoaded", () => {
		const resetBtn = document.getElementById("resetQueueBtn");
		if (resetBtn) {
			resetBtn.style.position = "fixed";
			resetBtn.style.top = "16px";
			resetBtn.style.right = "16px";
			resetBtn.style.zIndex = "1000";
			resetBtn.addEventListener("click", resetQueue);
		}

		if (toggleGenerationBtn) {
			toggleGenerationBtn.addEventListener("click", toggleGeneration);
		}

		if (toggleProtectionBtn) {
			toggleProtectionBtn.addEventListener("click", toggleProtection);
		}

		setupMetricsPanelPosition();
	});

	refreshQueueState();
	setInterval(refreshQueueState, 1000);
})();
