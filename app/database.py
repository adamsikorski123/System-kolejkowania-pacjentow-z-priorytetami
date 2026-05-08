import os
import sqlite3
import threading
from werkzeug.security import check_password_hash, generate_password_hash

class PatientDB:
    DEFAULT_MAX_RECORDS = 20

    def __init__(self, db_name=None, max_records=None, auth_db_name=None):
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

      
        self.patients_db_path = db_name or os.path.join(base_dir, "patients.db")
        self.auth_db_path = auth_db_name or os.path.join(base_dir, "users.db")

        env_max = os.getenv("PATIENT_DB_MAX_RECORDS")
        raw_max = max_records if max_records is not None else env_max
        try:
            parsed_max = int(raw_max) if raw_max is not None else self.DEFAULT_MAX_RECORDS
        except (TypeError, ValueError):
            parsed_max = self.DEFAULT_MAX_RECORDS

        self.max_records = max(1, parsed_max)
        self._lock = threading.Lock()

        self.patients_conn = sqlite3.connect(self.patients_db_path, check_same_thread=False)
        self.patients_cur = self.patients_conn.cursor()

        self.auth_conn = sqlite3.connect(self.auth_db_path, check_same_thread=False)
        self.auth_cur = self.auth_conn.cursor()

        with self._lock:
            self.patients_cur.execute("""
                CREATE TABLE IF NOT EXISTS patients (
                    id INTEGER PRIMARY KEY,
                    gender TEXT NOT NULL,
                    full_name TEXT NOT NULL,
                    arrival_time TEXT NOT NULL,
                    priority_number INTEGER,
                    service_time_seconds INTEGER
                )
            """)
            self.auth_cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    username TEXT PRIMARY KEY,
                    password_hash TEXT NOT NULL
                )
            """)
            self.patients_conn.commit()
            self.auth_conn.commit()

    def _enforce_max_records(self):
        self.patients_cur.execute("""
            DELETE FROM patients
            WHERE id NOT IN (
                SELECT id FROM patients
                ORDER BY id DESC
                LIMIT ?
            )
        """, (self.max_records,))

    def _get_patient_count(self) -> int:
        self.patients_cur.execute("SELECT COUNT(*) FROM patients")
        return int(self.patients_cur.fetchone()[0])

    def _delete_oldest_patients(self, count_to_delete: int):
        if count_to_delete <= 0:
            return
        self.patients_cur.execute(
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

            self.patients_cur.execute("SELECT 1 FROM patients WHERE id = ?", (patient_id,))
            exists = self.patients_cur.fetchone() is not None

            if not exists:
                current_count = self._get_patient_count()
                overflow = (current_count + 1) - self.max_records
                if overflow > 0:
                    self._delete_oldest_patients(overflow)

            self.patients_cur.execute("""
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
            self.patients_conn.commit()

    def delete_patient(self, patient_id: int):
        with self._lock:
            self.patients_cur.execute("DELETE FROM patients WHERE id = ?", (patient_id,))
            self.patients_conn.commit()

    def clear_all_patients(self):
        with self._lock:
            self.patients_cur.execute("DELETE FROM patients")
            self.patients_conn.commit()

    def get_next_patient_id(self) -> int:
        with self._lock:
            self.patients_cur.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM patients")
            return int(self.patients_cur.fetchone()[0])

    def get_all_patients(self):
        with self._lock:
            self.patients_cur.execute("""
                SELECT id, gender, full_name, arrival_time, priority_number, service_time_seconds
                FROM patients
                ORDER BY id
            """)
            rows = self.patients_cur.fetchall()

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
            self.auth_cur.execute("SELECT username FROM users WHERE username = ?", (username,))
            if self.auth_cur.fetchone() is None:
                self.auth_cur.execute(
                    "INSERT INTO users (username, password_hash) VALUES (?, ?)",
                    (username, generate_password_hash(password)),
                )
                self.auth_conn.commit()

    def verify_user(self, username: str, password: str) -> bool:
        with self._lock:
            self.auth_cur.execute("SELECT password_hash FROM users WHERE username = ?", (username,))
            row = self.auth_cur.fetchone()
        if not row:
            return False
        return check_password_hash(row[0], password)

    def add_user(self, username: str, password: str) -> bool:
        username = (username or "").strip()
        if not username or not password:
            return False

        with self._lock:
            self.auth_cur.execute("SELECT username FROM users WHERE username = ?", (username,))
            if self.auth_cur.fetchone() is not None:
                return False
            self.auth_cur.execute(
                "INSERT INTO users (username, password_hash) VALUES (?, ?)",
                (username, generate_password_hash(password)),
            )
            self.auth_conn.commit()
            return True

    def delete_user(self, username: str) -> bool:
        username = (username or "").strip()
        if not username:
            return False

        with self._lock:
            self.auth_cur.execute("DELETE FROM users WHERE username = ?", (username,))
            deleted = self.auth_cur.rowcount > 0
            self.auth_conn.commit()
            return deleted

    def list_users(self):
        with self._lock:
            self.auth_cur.execute("SELECT username FROM users ORDER BY username")
            rows = self.auth_cur.fetchall()
        return [r[0] for r in rows]