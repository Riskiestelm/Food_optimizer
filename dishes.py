import os
import json
import gspread
from google.oauth2.service_account import Credentials
from cooldown import is_on_cooldown
import random

SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
SHEET_ID = os.getenv("GOOGLE_SHEET_ID")
SHEET_TAB = "Dishes"


def _get_sheet():
    creds_json = os.getenv("GOOGLE_CREDENTIALS_JSON")
    if not creds_json:
        raise ValueError("GOOGLE_CREDENTIALS_JSON env var not set")
    creds_dict = json.loads(creds_json)
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    client = gspread.authorize(creds)
    return client.open_by_key(SHEET_ID).worksheet(SHEET_TAB)


def fetch_all_dishes() -> list[dict]:
    """Fetch all active dishes from Google Sheets."""
    sheet = _get_sheet()
    records = sheet.get_all_records()
    dishes = []
    for row in records:
        if str(row.get("active", "")).strip().upper() != "TRUE":
            continue
        name = str(row.get("name", "")).strip()
        dtype = str(row.get("type", "")).strip().lower()
        meal_raw = str(row.get("meal", "")).strip().lower()
        meals = [m.strip() for m in meal_raw.split(",") if m.strip()]
        if name and dtype and meals:
            dishes.append({"name": name, "type": dtype, "meals": meals})
    return dishes


def suggest_dish(dtype: str, meal: str) -> dict | None:
    """
    Suggest a random dish filtered by type and meal slot, excluding cooldowns.
    dtype: 'veg' or 'non-veg'
    meal: 'breakfast', 'lunch', or 'dinner'
    """
    all_dishes = fetch_all_dishes()
    available = [
        d for d in all_dishes
        if d["type"] == dtype
        and meal in d["meals"]
        and not is_on_cooldown(d["name"])
    ]
    if not available:
        return None
    return random.choice(available)


def suggest_both(meal: str) -> dict:
    """Suggest one veg and one non-veg dish for a given meal slot."""
    return {
        "veg": suggest_dish("veg", meal),
        "non-veg": suggest_dish("non-veg", meal)
    }
