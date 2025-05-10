import cv2
import pytesseract
import re

# Pokud nemáš tesseract v PATH, uprav sem:
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

def parse_vs_image(img_path: str, start_rank: int = 1):
    img = cv2.imread(img_path)
    if img is None:
        raise FileNotFoundError(f"Nepodařilo se načíst obrázek: {img_path}")
    h, w = img.shape[:2]

    # Vypočteme posuny a velikost řádku stejně, jak jsme testovali
    top_offset    = int(h * 0.20)
    bottom_offset = int(h * 0.05)
    region_h      = h - top_offset - bottom_offset
    row_h         = region_h // 7

    name_x1, name_x2 = int(w * 0.20), int(w * 0.55)
    pts_x1,  pts_x2  = int(w * 0.70), int(w * 0.95)

    rows = []
    for i in range(7):
        y1 = top_offset + i * row_h
        y2 = y1 + row_h

        roi_name = img[y1:y2, name_x1:name_x2]
        roi_pts  = img[y1:y2, pts_x1:pts_x2]

        name = pytesseract.image_to_string(
            roi_name,
            config='--psm 7 -c tessedit_char_blacklist=!?|/\\'
        ).strip()
        pts = pytesseract.image_to_string(
            roi_pts,
            config='--psm 7 -c tessedit_char_whitelist=0123456789,'
        ).strip()

        # Čištění
        name = re.sub(r'[^A-Za-z0-9\[\]áčďéěíňóřšťúůýžĂÂÇÉÍÓÚ]', '', name)
        pts  = re.sub(r'[^0-9,]', '', pts)

        if name and pts:
            rows.append((name, pts))

    # Odstraníme duplicitní Stepanekmi
    seen = set()
    clean = []
    for name, pts in rows:
        key = name.lower()
        if key.startswith('stepanekmi') and key in seen:
            continue
        clean.append((name, pts))
        seen.add(key)

    # Složení tabulky s ranky
    table = []
    for idx, (name, pts) in enumerate(clean):
        table.append((start_rank + idx, name, pts))
    return table
