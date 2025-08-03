import os
import csv
import datetime
from github import Github  # pip install PyGithub

GH_TOKEN = os.environ["GH_TOKEN"]
GH_OWNER = os.environ["GH_OWNER"]
GH_REPO  = os.environ["GH_REPO"]

def save_power_data(user, tank, rocket, air, team4=None):
    # Lokální append
    row = [datetime.datetime.utcnow().isoformat(), user, tank, rocket, air, team4 or ""]
    with open("power_data.csv", "a", newline="") as f:
        csv.writer(f).writerow(row)
    # Commit na GitHub
    gh   = Github(GH_TOKEN)
    repo = gh.get_repo(f"{GH_OWNER}/{GH_REPO}")
    path = "data/power_data.csv"
    content_file = repo.get_contents(path)
    with open("power_data.csv", "r") as f:
        data = f.read()
    repo.update_file(path, f"Power data by {user}", data, content_file.sha)

def save_vs_data(action, date=None, tag=None):
    # Podobně implementuj pro vs_data.csv
    pass
