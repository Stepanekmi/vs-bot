import os, base64, requests

GITHUB_REPO = "Stepanekmi/vs-data-store"
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

def save_to_github(local_file_path, repo_file_path, commit_msg="Update data"):
    with open(local_file_path, "rb") as f:
        content = base64.b64encode(f.read()).decode()
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{repo_file_path}"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json"
    }
    r = requests.get(url, headers=headers)
    sha = r.json().get("sha") if r.status_code == 200 else None
    data = {
        "message": commit_msg,
        "content": content,
        "branch": "main",
        "committer": {"name":"VS Bot","email":"vsbot@users.noreply.github.com"}
    }
    if sha:
        data["sha"] = sha
    requests.put(url, json=data, headers=headers)
