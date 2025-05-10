import requests
import base64
from io import BytesIO
import pandas as pd
import os

# Data uložíme do jednoduché CSV databáze
DB_FILE = "vs_data.csv"
if not os.path.exists(DB_FILE):
    pd.DataFrame(columns=["name", "points", "date", "tag"]).to_csv(DB_FILE, index=False)

def process_vs_images(image_bytes, date, tag):
    url = "https://api.ocr.space/parse/image"
    api_key = os.getenv("OCR_SPACE_API_KEY")

    response = requests.post(url, files={"file": image_bytes}, data={"apikey": api_key, "language": "eng", "OCREngine": 2})
    parsed = response.json()
    
    results = []
    if parsed["IsErroredOnProcessing"]:
        return results
    
    for line in parsed["ParsedResults"][0]["ParsedText"].split("\n"):
        if "[RoP]" in line and any(c.isdigit() for c in line):
            try:
                name = line.split("[RoP]")[0].strip()
                points = int("".join(filter(str.isdigit, line.split("[RoP]")[1])))
                results.append({"name": name, "points": points, "date": date, "tag": tag})
            except:
                continue

    # Uložit do CSV
    df = pd.read_csv(DB_FILE)
    df = pd.concat([df, pd.DataFrame(results)], ignore_index=True)
    df.to_csv(DB_FILE, index=False)
    return results

def get_top_day():
    df = pd.read_csv(DB_FILE)
    if df.empty:
        return "Žádná data."
    latest = df["date"].max()
    df_latest = df[df["date"] == latest].sort_values(by="points", ascending=False)
    return "\n".join([f"{row['name']}: {row['points']}" for _, row in df_latest.iterrows()])

def get_top_tag(tag):
    df = pd.read_csv(DB_FILE)
    df_tag = df[df["tag"] == tag]
    if df_tag.empty:
        return f"Žádná data pro zkratku {tag}."
    df_grouped = df_tag.groupby("name")["points"].sum().reset_index().sort_values(by="points", ascending=False)
    return "\n".join([f"{row['name']}: {row['points']}" for _, row in df_grouped.iterrows()])

def get_player_stats(name):
    df = pd.read_csv(DB_FILE)
    df_player = df[df["name"].str.lower() == name.lower()]
    if df_player.empty:
        return f"Nebyly nalezeny žádné statistiky pro hráče {name}."
    df_sorted = df_player.sort_values(by="date")
    return "\n".join([f"{row['date']} ({row['tag']}): {row['points']}" for _, row in df_sorted.iterrows()])
