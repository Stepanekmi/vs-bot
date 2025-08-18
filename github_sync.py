import os
import base64
import requests

GITHUB_REPO = "Stepanekmi/vs-data-store"
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")


def save_to_github(local_path: str, repo_path: str, message: str, branch: str = BRANCH) -> None:
    """Commit a local file to GitHub repo at the given path. Raises on failure."""
    if not GITHUB_TOKEN:
        print("⚠️  GITHUB_TOKEN not set – skipping GitHub commit")
        return
    if not os.path.exists(local_path):
        raise FileNotFoundError(f"Local file not found: {local_path}")

    with open(local_path, "rb") as f:
        content_b64 = base64.b64encode(f.read()).decode("utf-8")

    url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/{repo_path}"

    # Check if file exists to fetch SHA
    sha = None
    try:
        r_meta = session.get(url, params={"ref": branch}, timeout=DEFAULT_TIMEOUT)
        if r_meta.status_code == 200:
            data = r_meta.json()
            sha = data.get("sha")
        elif r_meta.status_code == 404:
            sha = None
        else:
            r_meta.raise_for_status()
    except requests.RequestException as e:
        raise RuntimeError(f"Failed to query existing file on GitHub: {e}") from e

    payload = {
        "message": message,
        "content": content_b64,
        "branch": branch
    }
    if sha:
        payload["sha"] = sha

    try:
        r_put = session.put(url, json=payload, timeout=DEFAULT_TIMEOUT)
        r_put.raise_for_status()
        print(f"✅  Committed {local_path} → {repo_path} ({branch}) : {message}")
    except requests.RequestException as e:
        # Try to surface API error details
        detail = None
        try:
            detail = r_put.json()
        except Exception:
            pass
        raise RuntimeError(f"GitHub commit failed: {e} | detail={detail}") from e
    requests.put(url, json=data, headers=headers)