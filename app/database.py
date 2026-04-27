import sqlite3

class PatientDB:
    def __init__(self, db_name="patients.db"):
        self.conn = sqlite3.connect(db_name, check_same_thread=False)
        self.cur = self.conn.cursor()
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
        self.conn.commit()

    def add_patient(self, patient_record):
        self.cur.execute("""
            INSERT OR REPLACE INTO patients
            (id, gender, full_name, arrival_time, priority_number, service_time_seconds)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            patient_record["id"],
            patient_record["gender"],
            patient_record["full_name"],
            patient_record["arrival_time"],
            patient_record.get("priority_number"),
            patient_record.get("service_time_seconds"),
        ))
        self.conn.commit()

    def get_all_patients(self):
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
                "priority_number": r[4],
                "service_time_seconds": r[5],
            }
            for r in rows
        ]