import os # standardowa biblioteka do obsługi systemu operacyjnego
from app.init import app # import obiektu app z modułu init.py, który jest instancją aplikacji Flask

if __name__ == '__main__':
    os.environ.setdefault("PATIENT_DB_MAX_RECORDS", "20") # Ustawienie domyślnej wartości dla maksymalnej liczby rekordów w bazie pacjentów (można nadpisać przez zmienną środowiskową)
    port = int(os.environ.get('PORT', 5000)) # Pobranie portu z zmiennej środowiskowej PORT, domyślnie 5000
    app.run(host='0.0.0.0', port=port, debug=False) # Uruchomienie aplikacji Flask, nasłuchiwanie na wszystkich interfejsach sieciowych (0.0.0.0)

