"""GitHub synchronizační helper pro vs‑data‑store.

• fetch_power_data()  — stáhne data/power_data.csv a vždy je zkopíruje na ./power_data.csv
• save_power_data(msg) — commitne power_data.csv do repozitáře na stejné cestě
• save_to_github(...)  — zpětně kompatibilní wrapper volající save_power_data
"""
from __future__ import annotations

import base64
import os
import shutil
from pathlib import Path
from typing import Final

import requests

# ------------- konfigurace -------------
OWNER:  Final[str] = os.getenv("GH_OWNER", "YOUR_GH_USER")
REPO:   Final[str] = os.getenv("GH_REPO", "vs-data-store")
TOKEN:  Final[str | None] = os.getenv("GH_TOKEN")
BRANCH: Final[str] = "main"

WORK_FILE: Final[Path] = Path("power_data.csv")           # pracovní soubor
REPO_FILE: Final[str]  = "data/power_data.csv"            # cesta v repozitáři
TMP_FILE:  Final[Path] = Path(REPO_FILE)                   # lokální kopie z fetch

SESSION = requests.Session()
SESSION.headers.update({
    "Authorization": f"token {TOKEN}" if TOKEN else "",
    "Accept": "application/vnd.github.v3+json",
    "User-Agent": "vs-bot-sync/1.0",
})

RAW_URL = f"https://raw.githubusercontent.com/{OWNER}/{REPO}/{BRANCH}/{REPO_FILE}"
API_URL = f"https://api.github.com/repos/{OWNER}/{REPO}/contents/{REPO_FILE}"


# ------------- fetch -------------

def _ensure_dirs() -> None:
    TMP_FILE.parent.mkdir(parents=True, exist_ok=True)


def fetch_power_data() -> None:
    """Stáhne CSV a přepíše pracovní kopii."""
    _ensure_dirs()
    print("📥  Fetching", RAW_URL)
    r = SESSION.get(RAW_URL, timeout=15)
    if r.status_code == 404:
        print("⚠️  Remote file not found – creating blank CSV")
        TMP_FILE.write_text("player,tank,rocket,air,timestamp\n")
    else:
        r.raise_for_status()
        TMP_FILE.write_bytes(r.content)
        print("✅  Fetched", REPO_FILE)

    shutil.copyfile(TMP_FILE, WORK_FILE)
    print("↪️  Updated", WORK_FILE)


# ------------- commit -------------

def _get_file_sha() -> str | None:
    r = SESSION.get(API_URL, timeout=15, params={"ref": BRANCH})
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.json().get("sha")


def save_power_data(message: str) -> None:
    """Commitne pracovní CSV do repozitáře."""
    if not TOKEN:
        print("⚠️  GH_TOKEN není nastaven – skip commit")
        return

    _ensure_dirs()
    shutil.copyfile(WORK_FILE, TMP_FILE)
    content_b64 = base64.b64encode(TMP_FILE.read_bytes()).decode()
    sha = _get_file_sha()

    payload = {
        "message": message,
        "content": content_b64,
        "branch": BRANCH,
    }
    if sha:
        payload["sha"] = sha

    r = SESSION.put(API_URL, timeout=15, json=payload)
    r.raise_for_status()
    print("✅  Committed to GitHub:", message)


# ------------- wrapper pro starý kód -------------

def save_to_github(_local_path: str, _repo_path: str, message: str):  # noqa: N802
    """Legacy API wrapper – forward na save_power_data."""
    print("ℹ️  save_to_github() wrapper → save_power_data()")
    save_power_data(message)
