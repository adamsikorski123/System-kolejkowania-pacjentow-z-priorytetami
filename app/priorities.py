"""
Definicja priorytetów pacjentów (1-5) z kolorami i czasami obsługi
"""

PRIORITY_CONFIG = {
    1: {
        "name": "niebieski",
        "color": "#0066cc",
        "service_time_seconds": 5,
    },
    2: {
        "name": "zielony",
        "color": "#00cc00",
        "service_time_seconds": 7,
    },
    3: {
        "name": "żółty",
        "color": "#ffcc00",
        "service_time_seconds": 10,
    },
    4: {
        "name": "pomarańczowy",
        "color": "#ff9900",
        "service_time_seconds": 15,
    },
    5: {
        "name": "czerwony",
        "color": "#ff0000",
        "service_time_seconds": 20,
    },
}

def get_service_time_for_priority(priority: int) -> int:
    """Zwraca czas obsługi w sekundach dla danego priorytetu"""
    return PRIORITY_CONFIG.get(priority, {}).get("service_time_seconds", 5)

def get_priority_name(priority: int) -> str:
    """Zwraca nazwę koloru priorytetu"""
    return PRIORITY_CONFIG.get(priority, {}).get("name", "nieznany")

def get_priority_color(priority: int) -> str:
    """Zwraca kod koloru dla danego priorytetu"""
    return PRIORITY_CONFIG.get(priority, {}).get("color", "#cccccc")
