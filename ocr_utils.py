
import easyocr

# Načti model pouze jednou
reader = easyocr.Reader(["en"], gpu=False)

def ocr_vs(pil_image) -> str:
    results = reader.readtext(pil_image)
    vysledky = []

    for box in results:
        text = box[1]
        parts = text.strip().split()
        if len(parts) >= 2:
            name = parts[0]
            score_raw = parts[-1].replace(',', '').replace('.', '')
            if score_raw.isdigit():
                vysledky.append(f"{name}: {score_raw}")

    return "\n".join(vysledky) if vysledky else "❌ OCR nerozpoznalo žádné VS výsledky."
