import os # standardowa biblioteka do obsługi systemu operacyjnego
import sqlite3 # standardowa biblioteka do obsługi baz danych SQLite
import threading # standardowa biblioteka do obsługi wątków
from werkzeug.security import check_password_hash, generate_password_hash # biblioteka do bezpiecznego hashowania haseł (część frameworka Flask, ale można używać osobno)

# Klasa PatientDB jest odpowiedzialna za zarządzanie bazą danych pacjentów oraz użytkowników (operatorów). Umożliwia dodawanie, usuwanie i pobieranie informacji o pacjentach, a także zarządzanie kontami użytkowników. Baza danych jest oparta na SQLite i jest zabezpieczona przed jednoczesnym dostępem z wielu wątków za pomocą blokady (threading.Lock). Klasa ta zapewnia również mechanizm ograniczania liczby przechowywanych rekordów pacjentów, aby uniknąć nadmiernego rozrostu bazy danych.
class PatientDB:
    DEFAULT_MAX_RECORDS = 20

    # Inicjalizacja klasy PatientDB, która tworzy połączenia z bazą danych pacjentów i użytkowników, tworzy odpowiednie tabele (jeśli nie istnieją) oraz ustawia maksymalną liczbę rekordów pacjentów, która może być przechowywana w bazie danych. Maksymalna liczba rekordów może być ustawiona przez argument max_records lub przez zmienną środowiskową PATIENT_DB_MAX_RECORDS. Jeśli oba te źródła są nieobecne lub nieprawidłowe, używana jest wartość domyślna DEFAULT_MAX_RECORDS.
    def __init__(self, db_name=None, max_records=None, auth_db_name=None):
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

      
        self.patients_db_path = db_name or os.path.join(base_dir, "patients.db") # Ustalamy ścieżkę do bazy danych pacjentów. Jeśli argument db_name jest podany, używamy go, w przeciwnym razie tworzymy ścieżkę do pliku "patients.db" w katalogu nadrzędnym względem tego pliku (czyli w głównym katalogu projektu).
        self.auth_db_path = auth_db_name or os.path.join(base_dir, "users.db") # Ustalamy ścieżkę do bazy danych użytkowników. Jeśli argument auth_db_name jest podany, używamy go, w przeciwnym razie tworzymy ścieżkę do pliku "users.db" w katalogu nadrzędnym względem tego pliku (czyli w głównym katalogu projektu).

        env_max = os.getenv("PATIENT_DB_MAX_RECORDS")
        raw_max = max_records if max_records is not None else env_max
        try:
            parsed_max = int(raw_max) if raw_max is not None else self.DEFAULT_MAX_RECORDS
        except (TypeError, ValueError):
            parsed_max = self.DEFAULT_MAX_RECORDS

        self.max_records = max(1, parsed_max)
        #!!! WSPÓŁBIEŻNOŚĆ Blokada do synchronizacji dostępu do bazy danych, aby uniknąć problemów z jednoczesnym dostępem z wielu wątków.
        self._lock = threading.Lock() 

        # Tworzymy połączenia z bazą danych pacjentów i użytkowników oraz kursory do wykonywania zapytań SQL. Ustawiamy check_same_thread=False, aby umożliwić dostęp do bazy danych z różnych wątków (co jest bezpieczne, ponieważ używamy blokady do synchronizacji dostępu).
        self.patients_conn = sqlite3.connect(self.patients_db_path, check_same_thread=False)
        self.patients_cur = self.patients_conn.cursor()

        self.auth_conn = sqlite3.connect(self.auth_db_path, check_same_thread=False)
        self.auth_cur = self.auth_conn.cursor()

            # !!! WSPÓŁBIEŻNOŚĆ
            # with self._lock: - zabezpieczamy tworzenie tabel przed jednoczesnym dostępem z wielu wątków, aby uniknąć problemów z konkurencją podczas inicjalizacji bazy danych.
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

    # Funkcja pomocnicza do usuwania najstarszych rekordów pacjentów, jeśli liczba rekordów przekracza maksymalną dozwoloną wartość (self.max_records). Usuwane są rekordy z najniższym id (najstarsze), aby utrzymać tylko najnowsze rekordy pacjentów w bazie danych.
    def _enforce_max_records(self): 
        self.patients_cur.execute("""
            DELETE FROM patients
            WHERE id NOT IN (
                SELECT id FROM patients
                ORDER BY id DESC
                LIMIT ?
            )
        """, (self.max_records,))

    # Funkcja pomocnicza do pobierania aktualnej liczby rekordów pacjentów w bazie danych. Wykonuje zapytanie SQL, które zwraca liczbę rekordów w tabeli patients, i zwraca tę wartość jako liczbę całkowitą.
    def _get_patient_count(self) -> int:
        self.patients_cur.execute("SELECT COUNT(*) FROM patients")
        return int(self.patients_cur.fetchone()[0])

    # Funkcja pomocnicza do usuwania określonej liczby najstarszych rekordów pacjentów z bazy danych. Przyjmuje argument count_to_delete, który określa, ile najstarszych rekordów ma zostać usuniętych. Jeśli count_to_delete jest mniejsze lub równe 0, funkcja nic nie robi. W przeciwnym razie wykonuje zapytanie SQL, które usuwa rekordy z tabeli patients, które mają id wśród najniższych (najstarszych) id, ograniczając się do liczby określonej przez count_to_delete.
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

    # Funkcja do dodawania lub aktualizowania rekordu pacjenta w bazie danych. Przyjmuje argument patient_record, który jest słownikiem zawierającym informacje
    def add_patient(self, patient_record):

        #!!! WSPÓŁBIEŻNOŚĆ Blokujemy dostęp do bazy danych podczas dodawania pacjenta, aby uniknąć problemów z jednoczesnym dostępem z wielu wątków. Sprawdzamy, czy rekord pacjenta o danym id już istnieje w bazie danych. Jeśli nie istnieje, sprawdzamy aktualną liczbę rekordów pacjentów i obliczamy, ile rekordów trzeba usunąć, aby nie przekroczyć maksymalnej liczby rekordów (self.max_records). Jeśli trzeba usunąć jakieś rekordy, wywołujemy funkcję _delete_oldest_patients, aby usunąć najstarsze rekordy. Następnie dodajemy lub aktualizujemy rekord pacjenta w bazie danych za pomocą zapytania SQL INSERT OR REPLACE. Na końcu zatwierdzamy zmiany w bazie danych.
        #with self._lock:
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

    # Funkcja do usuwania rekordu pacjenta z bazy danych na podstawie jego id. Przyjmuje argument patient_id, który jest identyfikatorem pacjenta do usunięcia. Blokujemy dostęp do bazy danych podczas tej operacji, aby uniknąć problemów z jednoczesnym dostępem z wielu wątków. Wykonujemy zapytanie SQL, które usuwa rekord z tabeli patients, który ma id równe patient_id. Na końcu zatwierdzamy zmiany w bazie danych.
    def delete_patient(self, patient_id: int):
        with self._lock:
            self.patients_cur.execute("DELETE FROM patients WHERE id = ?", (patient_id,))
            self.patients_conn.commit()
    # Funkcja do usuwania wszystkich rekordów pacjentów z bazy danych. Blokujemy dostęp do bazy danych podczas tej operacji, aby uniknąć problemów z jednoczesnym dostępem z wielu wątków. Wykonujemy zapytanie SQL, które usuwa wszystkie rekordy z tabeli patients. Na końcu zatwierdzamy zmiany w bazie danych.
    def clear_all_patients(self):
        with self._lock:
            self.patients_cur.execute("DELETE FROM patients")
            self.patients_conn.commit()
    # Funkcja do pobierania kolejnego dostępnego identyfikatora pacjenta. Blokujemy dostęp do bazy danych podczas tej operacji, aby uniknąć problemów z jednoczesnym dostępem z wielu wątków. Wykonujemy zapytanie SQL, które zwraca maksymalny id z tabeli patients i dodaje 1, aby uzyskać kolejny dostępny id. Jeśli tabela jest pusta, zwracamy 1 jako pierwszy id.
    def get_next_patient_id(self) -> int:
        with self._lock:
            self.patients_cur.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM patients")
            return int(self.patients_cur.fetchone()[0])
    # Funkcja do pobierania wszystkich rekordów pacjentów z bazy danych. Blokujemy dostęp do bazy danych podczas tej operacji, aby uniknąć problemów z jednoczesnym dostępem z wielu wątków. Wykonujemy zapytanie SQL, które zwraca wszystkie kolumny z tabeli patients, posortowane według id. Następnie przekształcamy wyniki zapytania na listę słowników, gdzie każdy słownik reprezentuje jednego pacjenta z odpowied
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
    # Funkcja do zapewnienia istnienia domyślnego użytkownika (operatora) w bazie danych. Przyjmuje opcjonalne argumenty username i password, które określają nazwę użytkownika i hasło dla domyślnego konta. Blokujemy dostęp do bazy danych podczas tej operacji, aby uniknąć problemów z jednoczesnym dostępem z wielu wątków. Sprawdzamy, czy użytkownik o podanej nazwie już istnieje w bazie danych. Jeśli nie istnieje, tworzymy nowe konto użytkownika z podaną nazwą i hasłem (hasło jest hashowane za pomocą funkcji generate_password_hash). Na końcu zatwierdzamy zmiany w bazie danych.
    def ensure_default_user(self, username="admin", password="admin123"):
        #!!! WSPÓŁBIEŻNOŚĆ
        with self._lock: # Blokujemy dostęp do bazy danych podczas tej operacji, aby uniknąć problemów z jednoczesnym dostępem z wielu wątków.
            self.auth_cur.execute("SELECT username FROM users WHERE username = ?", (username,))
            if self.auth_cur.fetchone() is None:
                self.auth_cur.execute(
                    "INSERT INTO users (username, password_hash) VALUES (?, ?)",
                    (username, generate_password_hash(password)),
                )
                self.auth_conn.commit()

    # Funkcja do weryfikacji danych logowania użytkownika. Przyjmuje argumenty username i password, które są nazwą użytkownika i hasłem do sprawdzenia. Blokujemy dostęp do bazy danych podczas tej operacji, aby uniknąć problemów z jednoczesnym dostępem z wielu wątków. Wykonujemy zapytanie SQL, które zwraca hash hasła dla użytkownika o podanej nazwie. Jeśli użytkownik nie istnieje, zwracamy False. Jeśli użytkownik istnieje, porównujemy podane hasło z hashem z bazy danych za pomocą funkcji check_password_hash i zwracamy wynik tego porównania (True lub False).
    def verify_user(self, username: str, password: str) -> bool:
        with self._lock:
            self.auth_cur.execute("SELECT password_hash FROM users WHERE username = ?", (username,))
            row = self.auth_cur.fetchone()
        if not row:
            return False
        return check_password_hash(row[0], password)

    # Funkcja do dodawania nowego użytkownika (operatora) do bazy danych. Przyjmuje argumenty username i password, które są nazwą użytkownika i hasłem dla nowego konta. Blokujemy dostęp do bazy danych podczas tej operacji, aby uniknąć problemów z jednoczesnym dostępem z wielu wątków. Sprawdzamy, czy nazwa użytkownika jest niepusta i czy hasło jest podane. Jeśli dane są nieprawidłowe, zwracamy False. Następnie sprawdzamy, czy użytkownik o podanej nazwie już istnieje w bazie danych. Jeśli istnieje, zwracamy False. Jeśli użytkownik nie istnieje, tworzymy nowe konto użytkownika z podaną nazwą i hasłem (hasło jest hashowane za pomocą funkcji generate_password_hash). Na końcu zatwierdzamy zmiany w bazie danych i zwracamy True, aby wskazać, że konto zostało pomyślnie dodane.
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

    # Funkcja do usuwania użytkownika (operatora) z bazy danych na podstawie jego nazwy użytkownika. Przyjmuje argument username, który jest nazwą użytkownika do usunięcia. Blokujemy dostęp do bazy danych podczas tej operacji, aby uniknąć problemów z jednoczesnym dostępem z wielu wątków. Sprawdzamy, czy nazwa użytkownika jest niepusta. Jeśli jest pusta, zwracamy False. Następnie wykonujemy zapytanie SQL, które usuwa rekord z tabeli users, który ma username równe podanej nazwie. Sprawdzamy, czy został usunięty jakiś rekord (rowcount > 0) i zatwierdzamy zmiany w bazie danych. Zwracamy True, jeśli konto zostało pomyślnie usunięte, lub False, jeśli nie znaleziono konta do usunięcia.
    def delete_user(self, username: str) -> bool:
        username = (username or "").strip()
        if not username:
            return False

        with self._lock:
            self.auth_cur.execute("DELETE FROM users WHERE username = ?", (username,))
            deleted = self.auth_cur.rowcount > 0
            self.auth_conn.commit()
            return deleted

    # Funkcja do pobierania listy wszystkich użytkowników (operatorów) z bazy danych. Blokujemy dostęp do bazy danych podczas tej operacji, aby uniknąć problemów z jednoczesnym dostępem z wielu wątków. Wykonujemy zapytanie SQL, które zwraca nazwy wszystkich użytkowników posortowane alfabetycznie. Zwracamy listę nazw użytkowników.
    def list_users(self):
        with self._lock:
            self.auth_cur.execute("SELECT username FROM users ORDER BY username")
            rows = self.auth_cur.fetchall()
        return [r[0] for r in rows]