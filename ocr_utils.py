
import easyocr

reader = easyocr.Reader(["en"], gpu=False)

def extract_vs_data(image_path):
    results = reader.readtext(image_path)
    parsed = []

    for box in results:
        text = box[1]
        parts = text.strip().split()
        if len(parts) >= 2:
            name = parts[0]
            score_raw = parts[-1].replace(",", "").replace(".", "")
            if score_raw.isdigit():
                parsed.append((name, int(score_raw)))

    return parsed
