
import os
import base64
import requests

# Repo in the form "owner/name"
GITHUB_REPO = os.getenv("GITHUB_REPO", "Stepanekmi/vs-data-store")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_BRANCH = os.getenv("GITHUB_BRANCH", "main")
DEFAULT_TIMEOUT = 20

session = requests.Session()
if GITHUB_TOKEN:
    session.headers.update({
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "vs-bot/1.0"
    })
else:
    session.headers.update({
        "Accept": "application/vnd.github+json",
        "User-Agent": "vs-bot/1.0"
    })

def _split_repo(repo: str):
    if "/" not in repo:
        raise ValueError("GITHUB_REPO must be 'owner/name'")
    owner, name = repo.split("/", 1)
    return owner, name

def fetch_from_repo(repo_file_path: str, local_file_path: str) -> bool:
    """
    Fetch a file from the repo into a local path.
    - Tries RAW URL first (works for public).
    - Falls back to Contents API (works with private if GITHUB_TOKEN is set).
    Returns True if fetched, False if not.
    """
    owner, name = _split_repo(GITHUB_REPO)
    # Try RAW
    raw_url = f"https://raw.githubusercontent.com/{owner}/{name}/{GITHUB_BRANCH}/{repo_file_path}"
    try:
        r = session.get(raw_url, timeout=DEFAULT_TIMEOUT)
        if r.status_code == 200 and r.content:
            with open(local_file_path, "wb") as f:
                f.write(r.content)
            print(f"✅ Fetched {repo_file_path} → {local_file_path} (RAW)")
            return True
    except requests.RequestException:
        pass

    # Fallback to API
    api_url = f"https://api.github.com/repos/{owner}/{name}/contents/{repo_file_path}?ref={GITHUB_BRANCH}"
    try:
        r = session.get(api_url, timeout=DEFAULT_TIMEOUT)
        if r.status_code == 200:
            data = r.json()
            content_b64 = data.get("content")
            if content_b64:
                content = base64.b64decode(content_b64)
                with open(local_file_path, "wb") as f:
                    f.write(content)
                print(f"✅ Fetched {repo_file_path} → {local_file_path} (API)")
                return True
    except requests.RequestException:
        pass

    print(f"⚠️ Fetch skipped/failed for {repo_file_path}")
    return False

def save_to_github(local_file_path: str, repo_file_path: str, commit_msg: str = "Update data", branch: str = None) -> None:
    """Commit a local file into the GitHub repository at repo_file_path on the given branch."""
    if branch is None:
        branch = GITHUB_BRANCH
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
    r_meta = session.get(url, params={"ref": branch}, timeout=DEFAULT_TIMEOUT)
    if r_meta.status_code == 200:
        sha = r_meta.json().get("sha")
    elif r_meta.status_code != 404:
        r_meta.raise_for_status()

    payload = {"message": commit_msg, "content": content_b64, "branch": branch}
    if sha:
        payload["sha"] = sha

    r_put = session.put(url, json=payload, timeout=DEFAULT_TIMEOUT)
    r_put.raise_for_status()
    print(f"✅  Committed {local_file_path} → {repo_file_path} on {branch}: {commit_msg}")
