import os
import base64
import requests
from typing import Optional, Tuple

GH_OWNER  = os.getenv("GH_OWNER", "stepanekmi")
GH_REPO   = os.getenv("GH_REPO",  "vs-data-store")
GH_TOKEN  = os.getenv("GH_TOKEN")          # musí mít contents:write
GH_BRANCH = os.getenv("GH_BRANCH", "main")

session = requests.Session()
session.headers.update({
    "Accept": "application/vnd.github+json",
    "User-Agent": "vs-bot/1.3"
})
if GH_TOKEN:
    session.headers.update({"Authorization": f"token {GH_TOKEN}"})


def _api_url(path: str) -> str:
    return f"https://api.github.com/repos/{GH_OWNER}/{GH_REPO}/contents/{path}"

def _raw_url(path: str) -> str:
    return f"https://raw.githubusercontent.com/{GH_OWNER}/{GH_REPO}/{GH_BRANCH}/{path}"


def fetch_from_repo(repo_file_path: str, local_file_path: str, prefer_api: bool = True) -> bool:
    """
    Stáhne repo soubor do local_file_path.
    Preferuje GitHub Contents API (bez CDN cache). RAW je fallback.
    """
    # 1) API (bez cache)
    if prefer_api:
        try:
            r = session.get(_api_url(repo_file_path), params={"ref": GH_BRANCH}, timeout=20)
            if r.status_code == 200:
                data = r.json()
                content_b64 = data.get("content")
                if content_b64:
                    content = base64.b64decode(content_b64)
                    with open(local_file_path, "wb") as f:
                        f.write(content)
                    print(f"✅ API fetched {repo_file_path} -> {local_file_path} ({len(content)} B)")
                    return True
                else:
                    print(f"⚠️ API fetch: no content for {repo_file_path}")
            else:
                print(f"⚠️ API fetch {repo_file_path} status={r.status_code} body={r.text[:200]}")
        except requests.RequestException as e:
            print(f"⚠️ API fetch error {repo_file_path}: {e}")

    # 2) RAW (může být cache pár minut)
    try:
        r = session.get(_raw_url(repo_file_path), timeout=20)
        if r.status_code == 200 and r.content:
            with open(local_file_path, "wb") as f:
                f.write(r.content)
            print(f"ℹ️ RAW fetched {repo_file_path} -> {local_file_path} ({len(r.content)} B)")
            return True
        else:
            print(f"ℹ️ RAW fetch {repo_file_path} status={r.status_code}")
    except requests.RequestException as e:
        print(f"ℹ️ RAW fetch error {repo_file_path}: {e}")

    return False


def get_remote_meta(repo_file_path: str) -> Tuple[Optional[str], Optional[int]]:
    r = session.get(_api_url(repo_file_path), params={"ref": GH_BRANCH}, timeout=20)
    if r.status_code == 200:
        j = r.json()
        return j.get("sha"), j.get("size")
    return None, None


def save_to_github(local_file_path: str, repo_file_path: str, message: str) -> Optional[str]:
    """Vytvoří/aktualizuje soubor v repu. Vrací novou content SHA nebo None (když chybí token)."""
    if not GH_TOKEN:
        print("⚠️ GH_TOKEN not set — skipping commit")
        return None
    if not os.path.exists(local_file_path):
        raise FileNotFoundError(f"Local file not found: {local_file_path}")

    with open(local_file_path, "rb") as f:
        content_b64 = base64.b64encode(f.read()).decode("utf-8")

    payload = {"message": message, "content": content_b64, "branch": GH_BRANCH}
    sha_before, _ = get_remote_meta(repo_file_path)
    if sha_before:
        payload["sha"] = sha_before

    r = session.put(_api_url(repo_file_path), json=payload, timeout=30)
    if r.status_code in (200, 201):
        out = r.json()
        new_sha = (out.get("content") or {}).get("sha")
        print(f"✅ Committed {local_file_path} -> {repo_file_path} (sha={new_sha})")
        return new_sha
    else:
        print(f"❌ Commit failed: status={r.status_code} body={r.text[:400]}")
        try:
            r.raise_for_status()
        except Exception as e:
            print(f"❌ raise_for_status: {e}")
        return None
