"""
Moduł generowania wykresów latencji i jittera do wyświetlania
w interfejsie webowym aplikacji.

Wykresy są generowane jako PNG w pamięci (io.BytesIO) i zwracane
przez Flask jako Response z mimetype 'image/png'.
Nie są zapisywane na dysk.

Endpointy w init.py wywołują funkcje tego modułu przy każdym odświeżeniu
przez przeglądarkę (co ~3 sekundy via JavaScript).
"""

import io
import matplotlib
matplotlib.use("Agg")  # backend bez GUI — rysowanie tylko do pamięci (io.BytesIO)
import matplotlib.pyplot as plt

# Minimalna liczba zarejestrowanych pomiarów potrzebna do narysowania wykresu.
# Poniżej tej wartości zwracany jest placeholder z komunikatem.
MIN_POINTS = 3


def _compute_jitter(values: list[float]) -> list[float]:
    # Jitter_N = |wartość_N - wartość_(N-1)|; pierwsza wartość zawsze = 0
    jitters = [0.0]
    for i in range(1, len(values)):
        jitters.append(abs(values[i] - values[i - 1]))
    return jitters


def _placeholder_png(message: str) -> bytes:
    # Zwraca prosty PNG z tekstem gdy za mało danych do wykresu
    fig, ax = plt.subplots(figsize=(7, 3))
    ax.text(0.5, 0.5, message, ha="center", va="center",
            fontsize=12, color="#999999", transform=ax.transAxes,
            multialignment="center")
    ax.set_facecolor("#f8f8f8")
    ax.axis("off")
    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=100, bbox_inches="tight",
                facecolor="#f8f8f8")
    plt.close()
    buf.seek(0)
    return buf.getvalue()


def _to_png(fig) -> bytes:
    # Zapisuje figurę matplotlib do bajtów PNG i zwalnia pamięć
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=120, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf.getvalue()


def generate_latency_png(history: list[float], title: str) -> bytes:
    """
    Wykres latencji HTTP per operacja.
    Oś X: numer kolejnej operacji (1, 2, 3, …).
    Oś Y: czas odpowiedzi w ms.
    Gdy mniej niż MIN_POINTS pomiarów — zwraca placeholder.
    """
    n = len(history)
    if n < MIN_POINTS:
        return _placeholder_png(
            f"Zbieranie danych…\n({n} / {MIN_POINTS} pomiarów)"
        )

    rounds = list(range(1, n + 1))

    fig, ax = plt.subplots(figsize=(8, 3.8))
    ax.plot(rounds, history, color="#2196F3", linewidth=1.8,
            marker="o", markersize=4, zorder=2, label="latencja [ms]")
    ax.set_title(f"Latencja HTTP — {title}", fontsize=12, fontweight="bold")
    ax.set_xlabel("Numer operacji")
    ax.set_ylabel("Latencja [ms]")
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    return _to_png(fig)


def generate_jitter_png(history: list[float], title: str) -> bytes:
    """
    Wykres jittera latencji HTTP per operacja.
    Jitter_N = |latencja_N - latencja_(N-1)|.
    Gdy mniej niż MIN_POINTS pomiarów — zwraca placeholder.
    """
    n = len(history)
    if n < MIN_POINTS:
        return _placeholder_png(
            f"Zbieranie danych…\n({n} / {MIN_POINTS} pomiarów)"
        )

    rounds = list(range(1, n + 1))
    jitters = _compute_jitter(history)

    fig, ax = plt.subplots(figsize=(8, 3.8))
    ax.plot(rounds, jitters, color="#F44336", linewidth=1.8,
            marker="s", markersize=4, zorder=2, label="jitter [ms]")
    ax.set_title(f"Jitter latencji — {title}", fontsize=12, fontweight="bold")
    ax.set_xlabel("Numer operacji")
    ax.set_ylabel("Jitter [ms]")
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    return _to_png(fig)
