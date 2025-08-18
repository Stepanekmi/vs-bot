import os
import base64
import requests

# Repo in the form "owner/name"
GITHUB_REPO = os.getenv("GITHUB_REPO", "Stepanekmi/vs-data-store")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
DEFAULT_TIMEOUT = 20

session = requests.Session()
if GITHUB_TOKEN:
    session.headers.update({
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "vs-bot/1.0"
    })

def _split_repo(repo: str):
    if "/" not in repo:
        raise ValueError("GITHUB_REPO must be 'owner/name'")
    owner, name = repo.split("/", 1)
    return owner, name

def save_to_github(local_file_path: str, repo_file_path: str, commit_msg: str = "Update data", branch: str = "main") -> None:
    """Commit a local file into the GitHub repository at repo_file_path on the given branch."""
    if not GITHUB_TOKEN:
        print("⚠️  GITHUB_TOKEN not set – skipping GitHub commit")
        return
    if not os.path.exists(local_file_path):
        raise FileNotFoundError(f"Local file not found: {local_file_path}")

    owner, name = _split_repo(GITHUB_REPO)
    url = f"https://api.github.com/repos/{owner}/{name}/contents/{repo_file_path}"

    with open(local_file_path, "rb") as f:
        content_b64 = base64.b64encode(f.read()).decode("utf-8")

    # Detect existing file to get its SHA
    sha = None
    try:
        r_meta = session.get(url, params={"ref": branch}, timeout=DEFAULT_TIMEOUT)
        if r_meta.status_code == 200:
            sha = r_meta.json().get("sha")
        elif r_meta.status_code != 404:
            r_meta.raise_for_status()
    except requests.RequestException as e:
        raise RuntimeError(f"Failed to query existing file on GitHub: {e}") from e

    payload = {"message": commit_msg, "content": content_b64, "branch": branch}
    if sha:
        payload["sha"] = sha

    try:
        r_put = session.put(url, json=payload, timeout=DEFAULT_TIMEOUT)
        r_put.raise_for_status()
        print(f"✅  Committed {local_file_path} → {repo_file_path} on {branch}: {commit_msg}")
    except requests.RequestException as e:
        detail = None
        try:
            detail = r_put.json()
        except Exception:
            pass
        raise RuntimeError(f"GitHub commit failed: {e} | detail={detail}") from e
