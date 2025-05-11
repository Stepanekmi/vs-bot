import base64
import requests
import os

GITHUB_REPO = "Stepanekmi/vs-data-store"  # změň podle skutečnosti
GITHUB_BRANCH = "main"
GITHUB_API = "https://api.github.com"
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

headers = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json"
}

def save_to_github(local_file_path, repo_file_path, commit_msg="Update data"):
    # Získání obsahu souboru
    with open(local_file_path, "rb") as f:
        content = base64.b64encode(f.read()).decode()

    # Zjistíme, jestli soubor už existuje (kvůli SHA)
    url = f"{GITHUB_API}/repos/{GITHUB_REPO}/contents/{repo_file_path}"
    r = requests.get(url, headers=headers)
    sha = r.json().get("sha") if r.status_code == 200 else None

    data = {
        "message": commit_msg,
        "content": content,
        "branch": GITHUB_BRANCH,
        "committer": {
            "name": "VS Bot",
            "email": "vsbot@users.noreply.github.com"
        }
    }
    if sha:
        data["sha"] = sha

    response = requests.put(url, json=data, headers=headers)
    if response.status_code in (200, 201):
        print(f"✅ GitHub sync: {repo_file_path}")
    else:
        print(f"❌ GitHub sync error: {response.status_code}, {response.text}")
