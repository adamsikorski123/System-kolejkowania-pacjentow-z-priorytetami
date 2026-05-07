import os
import sqlite3
import threading
from werkzeug.security import check_password_hash, generate_password_hash

class PatientDB:
    DEFAULT_MAX_RECORDS = 20

    def __init__(self, db_name=None, max_records=None):
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        preferred_path = db_name or os.path.join(base_dir, "patient.db")
        legacy_path = os.path.join(base_dir, "patients.db")

        # Jeśli nie podano ścieżki i istnieje stary plik, użyj go (kompatybilność)
        self.db_path = preferred_path
        if db_name is None and not os.path.exists(preferred_path) and os.path.exists(legacy_path):
            self.db_path = legacy_path

        env_max = os.getenv("PATIENT_DB_MAX_RECORDS")
        raw_max = max_records if max_records is not None else env_max

        try:
            parsed_max = int(raw_max) if raw_max is not None else self.DEFAULT_MAX_RECORDS
        except (TypeError, ValueError):
            parsed_max = self.DEFAULT_MAX_RECORDS

        self.max_records = max(1, parsed_max)
        self._lock = threading.Lock()
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.cur = self.conn.cursor()

        with self._lock:
            self.cur.execute("""
                CREATE TABLE IF NOT EXISTS patients (
                    id INTEGER PRIMARY KEY,
                    gender TEXT NOT NULL,
                    full_name TEXT NOT NULL,
                    arrival_time TEXT NOT NULL,
                    priority_number INTEGER,
                    service_time_seconds INTEGER
                )
            """)
            self.cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    username TEXT PRIMARY KEY,
                    password_hash TEXT NOT NULL
                )
            """)
            self.conn.commit()

    def _enforce_max_records(self):
        self.cur.execute("""
            DELETE FROM patients
            WHERE id NOT IN (
                SELECT id FROM patients
                ORDER BY id DESC
                LIMIT ?
            )
        """, (self.max_records,))

    def _get_patient_count(self) -> int:
        self.cur.execute("SELECT COUNT(*) FROM patients")
        return int(self.cur.fetchone()[0])

    def _delete_oldest_patients(self, count_to_delete: int):
        if count_to_delete <= 0:
            return
        self.cur.execute(
            """
            DELETE FROM patients
            WHERE id IN (
                SELECT id FROM patients
                ORDER BY id ASC
                LIMIT ?
            )
            """,
            (count_to_delete,),
        )

    def add_patient(self, patient_record):
        with self._lock:
            patient_id = patient_record["id"]

            self.cur.execute("SELECT 1 FROM patients WHERE id = ?", (patient_id,))
            exists = self.cur.fetchone() is not None

            if not exists:
                current_count = self._get_patient_count()
                overflow = (current_count + 1) - self.max_records
                if overflow > 0:
                    self._delete_oldest_patients(overflow)

            self.cur.execute("""
                INSERT OR REPLACE INTO patients
                (id, gender, full_name, arrival_time, priority_number, service_time_seconds)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                patient_record["id"],
                patient_record["gender"],
                patient_record["full_name"],
                patient_record["arrival_time"],
                patient_record.get("priority"),
                patient_record.get("service_time_seconds"),
            ))
            self.conn.commit()

    def delete_patient(self, patient_id: int):
        with self._lock:
            self.cur.execute("DELETE FROM patients WHERE id = ?", (patient_id,))
            self.conn.commit()

    def clear_all_patients(self):
        with self._lock:
            self.cur.execute("DELETE FROM patients")
            self.conn.commit()

    def get_next_patient_id(self) -> int:
        with self._lock:
            self.cur.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM patients")
            return int(self.cur.fetchone()[0])

    def get_all_patients(self):
        with self._lock:
            self.cur.execute("""
                SELECT id, gender, full_name, arrival_time, priority_number, service_time_seconds
                FROM patients
                ORDER BY id
            """)
            rows = self.cur.fetchall()

        return [
            {
                "id": r[0],
                "gender": r[1],
                "full_name": r[2],
                "arrival_time": r[3],
                "priority": r[4],
                "service_time_seconds": r[5],
            }
            for r in rows
        ]

    def ensure_default_user(self, username="admin", password="admin123"):
        with self._lock:
            self.cur.execute("SELECT username FROM users WHERE username = ?", (username,))
            if self.cur.fetchone() is None:
                self.cur.execute(
                    "INSERT INTO users (username, password_hash) VALUES (?, ?)",
                    (username, generate_password_hash(password)),
                )
                self.conn.commit()

    def verify_user(self, username: str, password: str) -> bool:
        with self._lock:
            self.cur.execute("SELECT password_hash FROM users WHERE username = ?", (username,))
            row = self.cur.fetchone()
        if not row:
            return False
        return check_password_hash(row[0], password)

    def add_user(self, username: str, password: str) -> bool:
        username = (username or "").strip()
        if not username or not password:
            return False

        with self._lock:
            self.cur.execute("SELECT username FROM users WHERE username = ?", (username,))
            if self.cur.fetchone() is not None:
                return False
            self.cur.execute(
                "INSERT INTO users (username, password_hash) VALUES (?, ?)",
                (username, generate_password_hash(password)),
            )
            self.conn.commit()
            return True

    def delete_user(self, username: str) -> bool:
        username = (username or "").strip()
        if not username:
            return False

        with self._lock:
            self.cur.execute("DELETE FROM users WHERE username = ?", (username,))
            deleted = self.cur.rowcount > 0
            self.conn.commit()
            return deleted

    def list_users(self):
        with self._lock:
            self.cur.execute("SELECT username FROM users ORDER BY username")
            rows = self.cur.fetchall()
        return [r[0] for r in rows]