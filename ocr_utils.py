
import requests
import base64
from PIL import Image
import io
import os

# API klíč (volitelně můžeš použít zdarma nebo vlastní)
OCR_SPACE_API_KEY = os.getenv("OCR_SPACE_API_KEY", "helloworld")  # 'helloworld' je demo klíč s omezením

def ocr_vs(pil_image: Image.Image) -> str:
    buffered = io.BytesIO()
    pil_image.save(buffered, format="PNG")
    img_str = base64.b64encode(buffered.getvalue()).decode()

    url = "https://api.ocr.space/parse/image"
    payload = {
        "base64Image": "data:image/png;base64," + img_str,
        "language": "eng",
        "isOverlayRequired": False,
    }
    headers = {
        "apikey": OCR_SPACE_API_KEY
    }

    response = requests.post(url, data=payload, headers=headers)
    try:
        result = response.json()
        parsed_text = result["ParsedResults"][0]["ParsedText"]
        return parsed_text.strip() if parsed_text else "❌ OCR nevrátil žádný text."
    except Exception as e:
        return f"❌ Chyba při komunikaci s OCR API: {e}"
