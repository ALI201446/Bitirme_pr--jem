"""
Basit JSON tabanlı kullanıcı profili deposu.
İleride kolayca SQLite/PostgreSQL'e geçirilebilir; arayüz aynı kalır.
"""
import json
import os
from threading import Lock

PROFILE_PATH = os.path.join(os.path.dirname(__file__), "data", "user_profiles.json")
_lock = Lock()


def _load_all() -> dict:
    if not os.path.exists(PROFILE_PATH):
        return {}
    with open(PROFILE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_all(data: dict) -> None:
    with open(PROFILE_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_profile(user_id: int) -> dict:
    with _lock:
        data = _load_all()
    return data.get(str(user_id), {"history": [], "last_answers": []})


def save_profile(user_id: int, qa_pairs, recommended: list) -> None:
    """
    qa_pairs: [(soru, cevap), ...]
    recommended: son önerilen meslek isimleri listesi
    """
    with _lock:
        data = _load_all()
        profile = data.get(str(user_id), {"history": [], "last_answers": []})

        profile["last_answers"] = [{"question": q, "answer": a} for q, a in qa_pairs]
        profile["history"].append(recommended)

        data[str(user_id)] = profile
        _save_all(data)