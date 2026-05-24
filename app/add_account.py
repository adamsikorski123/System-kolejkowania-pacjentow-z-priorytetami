from pathlib import Path # standardowa biblioteka do obsługi ścieżek
from database import PatientDB # import klasy PatientDB z modułu database.py


# Prosty skrypt do zarządzania kontami użytkowników (operatorów) w bazie danych. Umożliwia dodawanie, usuwanie i wyświetlanie aktualnych użytkowników.
def print_help():
    print("\n=== Zarządzanie kontami ===")
    print("Dostępne komendy:")
    print("  add     - dodaj konto")
    print("  delete  - usuń konto ")
    print("  list    - pokaż aktualnych użytkowników")
    print("  exit    - wyjście\n")

# Główna funkcja skryptu, która tworzy instancję bazy danych pacjentów (PatientDB) i w pętli obsługuje komendy użytkownika do zarządzania kontami. Użytkownik może dodawać nowe konta, usuwać istniejące konta oraz wyświetlać listę aktualnych użytkowników. Skrypt działa w trybie interaktywnym, aż do momentu wpisania komendy "exit".
def main():
    project_root = Path(__file__).resolve().parents[1]
    patients_db = str(project_root / "patients.db")
    users_db = str(project_root / "users.db")

    db = PatientDB(db_name=patients_db, auth_db_name=users_db)
    print_help()

    while True:
        command = input("Wpisz komendę: ").strip().lower()

        if command == "add":
            username = input("Login: ").strip()
            password = input("Hasło: ").strip()
            ok = db.add_user(username, password)
            print("Konto dodane." if ok else "Nie udało się dodać konta (może już istnieje lub dane są puste).")

        elif command == "delete":
            username = input("Login do usunięcia: ").strip()
            ok = db.delete_user(username)
            print("Konto usunięte." if ok else "Nie znaleziono konta do usunięcia.")

        elif command == "list":
            users = db.list_users()
            if not users:
                print("Brak użytkowników.")
            else:
                print("Aktualni użytkownicy:")
                for u in users:
                    print(f" - {u}")

        elif command == "help":
            print_help()

        elif command == "exit":
            print("Zamykanie programu.")
            break

        else:
            print("Nieznana komenda. Wpisz 'help'.")


if __name__ == "__main__":
    main()
