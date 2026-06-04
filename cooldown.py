import json
import os
from datetime import date, timedelta

COOLDOWN_FILE = "cooldown.json"
COOLDOWN_DAYS = 3


def _load() -> dict:
    if not os.path.exists(COOLDOWN_FILE):
        return {}
    with open(COOLDOWN_FILE, "r") as f:
        return json.load(f)


def _save(data: dict):
    with open(COOLDOWN_FILE, "w") as f:
        json.dump(data, f, indent=2)


def mark_cooked(dish_name: str):
    """Record today as the last cooked date for a dish."""
    data = _load()
    data[dish_name] = date.today().isoformat()
    _save(data)


def is_on_cooldown(dish_name: str) -> bool:
    """Return True if the dish was cooked within the last COOLDOWN_DAYS days."""
    data = _load()
    if dish_name not in data:
        return False
    last_cooked = date.fromisoformat(data[dish_name])
    return (date.today() - last_cooked).days < COOLDOWN_DAYS


def get_cooldown_info(dish_name: str) -> str:
    """Return a human-readable string about when the dish becomes available."""
    data = _load()
    if dish_name not in data:
        return "Available now"
    last_cooked = date.fromisoformat(data[dish_name])
    unlock_date = last_cooked + timedelta(days=COOLDOWN_DAYS)
    days_left = (unlock_date - date.today()).days
    if days_left <= 0:
        return "Available now"
    return f"Available in {days_left} day(s) (unlocks {unlock_date.strftime('%a, %d %b')})"


def get_recent_history(limit: int = 10) -> list[dict]:
    """Return recently cooked dishes sorted by date descending."""
    data = _load()
    sorted_dishes = sorted(data.items(), key=lambda x: x[1], reverse=True)
    result = []
    for dish, cooked_date in sorted_dishes[:limit]:
        result.append({
            "dish": dish,
            "cooked_on": cooked_date,
            "status": get_cooldown_info(dish)
        })
    return result
