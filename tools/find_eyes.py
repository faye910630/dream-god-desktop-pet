# -*- coding: utf-8 -*-
import json
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ART = Path(r"d:\CODE\dream-god-desktop-pet\assets\psd_import\untitled62")
meta = [r for r in json.loads((ART / "layers.json").read_text(encoding="utf-8")) if r.get("nonempty")]
S = 512
yy, xx = np.mgrid[0:S, 0:S]
eye = (xx > S * 0.34) & (xx < S * 0.66) & (yy > S * 0.18) & (yy < S * 0.42)
font = ImageFont.truetype("C:/Windows/Fonts/msjh.ttc", 16)
sheet_rows = []
print("--- eye box ---")
for i, rec in enumerate(meta):
    a = np.asarray(Image.open(ART / rec["full"]).convert("RGBA").resize((S, S), Image.Resampling.BOX))
    m = (a[:, :, 3] > 30) & eye
    n = int(m.sum())
    if n < 25:
        continue
    bri = float(a[m][:, :3].mean())
    # skip the solid head caps
    if n > 8000:
        print(f"SKIP cap n={n} bri={bri:.0f} {rec['key']}")
        continue
    print(f"n={n:5d} bri={bri:5.0f} {rec['key']}")
    im = Image.open(ART / rec["full"]).convert("RGBA").resize((S, S), Image.Resampling.BILINEAR)
    crop = im.crop((int(S * 0.28), int(S * 0.12), int(S * 0.72), int(S * 0.48)))
    bg = Image.new("RGB", crop.size, (0, 0, 0))
    bg.paste(crop, mask=crop.split()[-1])
    d = ImageDraw.Draw(bg)
    d.text((4, 4), rec["key"][-28:], fill=(255, 220, 80), font=font)
    sheet_rows.append(bg)

if sheet_rows:
    w, h = sheet_rows[0].size
    cols = 4
    rows = (len(sheet_rows) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * w, rows * h), (0, 0, 0))
    for i, im in enumerate(sheet_rows):
        sheet.paste(im, ((i % cols) * w, (i // cols) * h))
    sheet.save(ART / "preview" / "eye_layers.png")
    print("saved", len(sheet_rows))
