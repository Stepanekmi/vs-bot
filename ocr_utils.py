
import pytesseract
from PIL import Image
import re

# OCR funkce s použitím pytesseract
def ocr_vs(pil_image: Image.Image) -> str:
    text = pytesseract.image_to_string(pil_image, config='--psm 6')
    lines = text.splitlines()
    vysledky = []

    for line in lines:
        match = re.search(r"([A-Za-z0-9_]+)\s+(\d{1,3}(?:[.,]\d{3})+)", line)
        if match:
            name = match.group(1)
            score = match.group(2).replace(",", "").replace(".", "")
            vysledky.append(f"{name}: {score}")

    return "\n".join(vysledky) if vysledky else "❌ OCR nerozpoznalo žádné VS výsledky."
