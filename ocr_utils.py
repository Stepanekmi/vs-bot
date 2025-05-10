import easyocr
import cv2
import numpy as np

reader = easyocr.Reader(['en'], gpu=False)

def parse_vs_image(img_bytes: bytes) -> list[tuple[str, str, str]]:
    arr = np.frombuffer(img_bytes, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)

    rows = []
    row_positions = [
        (150, 120), (280, 120), (410, 120), (540, 120),
        (670, 120), (800, 120), (930, 120), (1060, 120),
    ]
    rank_box = (100, 0, 100, 120)
    name_box = (200, 0, 400, 120)
    pts_box  = (600, 0, 200, 120)

    for y, h in row_positions:
        roi = img[y:y+h, :]
        x, dy, w, dh = rank_box
        rank_img = roi[dy:dy+dh, x:x+w]
        rank_txt = reader.readtext(rank_img, detail=0, paragraph=False)
        rank = rank_txt[0] if rank_txt else ""

        x, dy, w, dh = name_box
        name_img = roi[dy:dy+dh, x:x+w]
        name_txt = reader.readtext(name_img, detail=0)
        name = name_txt[0] if name_txt else ""

        x, dy, w, dh = pts_box
        pts_img = roi[dy:dy+dh, x:x+w]
        pts_txt = reader.readtext(pts_img, detail=0)
        pts = pts_txt[0] if pts_txt else ""

        if rank and name and pts:
            pts = pts.replace(" ", "").replace(".", ",")
            rows.append((rank.strip(), name.strip(), pts.strip()))

    return rows