from collections import deque # standardowa biblioteka do obsługi kolejek o stałej długości
import threading # standardowa biblioteka do obsługi wątków


class LatencyJitterMeter:
    def __init__(self, max_samples: int = 300):
        self._api_latency_ms = deque(maxlen=max_samples)
        self._queue_wait_s = deque(maxlen=max_samples)
        self._lock = threading.Lock()

    @staticmethod
    def _avg(values):
        return (sum(values) / len(values)) if values else 0.0

    @staticmethod
    def _jitter(values):
        if len(values) < 2:
            return 0.0
        diffs = [abs(values[i] - values[i - 1]) for i in range(1, len(values))]
        return sum(diffs) / len(diffs)

    def record_api_latency_ms(self, value: float):
        with self._lock:
            self._api_latency_ms.append(float(value))

    def record_queue_wait_s(self, value: float):
        with self._lock:
            self._queue_wait_s.append(float(value))

    def snapshot(self):
        with self._lock:
            api = list(self._api_latency_ms)
            qwait = list(self._queue_wait_s)

        return {
            "api_latency_last_ms": round(api[-1], 2) if api else 0.0,
            "api_latency_avg_ms": round(self._avg(api), 2),
            "api_latency_jitter_ms": round(self._jitter(api), 2),
            "queue_wait_last_s": round(qwait[-1], 2) if qwait else 0.0,
            "queue_wait_avg_s": round(self._avg(qwait), 2),
            "queue_wait_jitter_s": round(self._jitter(qwait), 2),
        }
