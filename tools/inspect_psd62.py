# -*- coding: utf-8 -*-
import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

p = Path(r"d:\CODE\dream-god-desktop-pet\assets\psd_import\untitled62")
meta = json.loads((p / "layers.json").read_text(encoding="utf-8"))
rows = [r for r in meta if r.get("nonempty")]
print("nonempty", len(rows))
for r in rows:
    cb = r["content_bbox"]
    area = (cb[2] - cb[0]) * (cb[3] - cb[1])
    print(f"{r['key']:45s} {r['name']!r:12s} area={area:8d} bbox={cb}")

# contact sheet of crops (scaled down)
cols = 6
thumb = 220
pad = 8
n = len(rows)
rows_n = (n + cols - 1) // cols
sheet = Image.new("RGBA", (cols * (thumb + pad) + pad, rows_n * (thumb + 40 + pad) + pad), (30, 28, 40, 255))
draw = ImageDraw.Draw(sheet)
try:
    font = ImageFont.truetype("C:/Windows/Fonts/msjh.ttc", 14)
except Exception:
    font = ImageFont.load_default()

for i, r in enumerate(rows):
    img = Image.open(p / r["file"]).convert("RGBA")
    # fit thumb
    s = min(thumb / max(img.width, 1), thumb / max(img.height, 1), 1.0)
    tw, th = max(1, int(img.width * s)), max(1, int(img.height * s))
    t = img.resize((tw, th), Image.Resampling.LANCZOS)
    cx = pad + (i % cols) * (thumb + pad)
    cy = pad + (i // cols) * (thumb + 40 + pad)
    # checker
    for yy in range(0, thumb, 16):
        for xx in range(0, thumb, 16):
            c = (55, 52, 70, 255) if ((xx // 16) + (yy // 16)) % 2 == 0 else (40, 38, 52, 255)
            draw.rectangle([cx + xx, cy + yy, cx + xx + 15, cy + yy + 15], fill=c)
    sheet.alpha_composite(t, (cx + (thumb - tw) // 2, cy + (thumb - th) // 2))
    label = f"{i}:{r['name']}"
    draw.text((cx, cy + thumb + 2), label[:28], fill=(230, 220, 255, 255), font=font)
    draw.text((cx, cy + thumb + 18), r["key"][-28:], fill=(160, 150, 180, 255), font=font)

sheet.save(p / "__contact.png")
# also smaller composite preview
comp = Image.open(p / "__composite.png").convert("RGBA")
comp.resize((512, 512), Image.Resampling.LANCZOS).save(p / "__composite_512.png")
print("wrote contact + composite preview")
