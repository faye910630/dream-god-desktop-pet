# -*- coding: utf-8 -*-
"""Classify untitled62 PSD layers by position / size / color into L2D part roles."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(r"d:\CODE\dream-god-desktop-pet\assets\psd_import\untitled62")
OUT = ROOT / "labeled"
OUT.mkdir(exist_ok=True)

meta = json.loads((ROOT / "layers.json").read_text(encoding="utf-8"))
rows = [r for r in meta if r.get("nonempty")]


def stats(r):
    img = np.asarray(Image.open(ROOT / r["full"]).convert("RGBA"))
    a = img[:, :, 3] > 8
    if not a.any():
        return None
    ys, xs = np.nonzero(a)
    rgb = img[a, :3].astype(np.float32)
    return {
        "key": r["key"],
        "name": r["name"],
        "file": r["file"],
        "full": r["full"],
        "x0": int(xs.min()),
        "x1": int(xs.max()),
        "y0": int(ys.min()),
        "y1": int(ys.max()),
        "cx": float(xs.mean()),
        "cy": float(ys.mean()),
        "w": int(xs.max() - xs.min() + 1),
        "h": int(ys.max() - ys.min() + 1),
        "area": int(a.sum()),
        "mean_rgb": tuple(map(int, rgb.mean(0))),
        "bri": float(rgb.mean()),
    }


all_s = [stats(r) for r in rows]
all_s = [s for s in all_s if s]

# Heuristic labels
# Character roughly: x 450-1600, y 46-1872, face center ~1024,550-700
FACE_CY = 620
HEAD_TOP = 150
NECK_Y = 780
SKIRT_Y = 1100


def guess(s):
    cy, cx, w, h, area, bri = s["cy"], s["cx"], s["w"], s["h"], s["area"], s["bri"]
    # tiny mouth / highlight
    if area < 800 and 800 < cy < 900:
        return "mouth_dot"
    if area < 1200 and 820 < cy < 880 and 1000 < cx < 1050:
        return "highlight"
    # eye band
    if 540 < cy < 700 and area < 45000:
        if bri > 180 and h < 40 and w > 250:
            return "brow_or_lash"
        if bri > 200 and 15 < h < 90 and 80 < w < 450:
            if cx < 1024:
                return "iris_L_cand"
            if cx > 1024:
                return "iris_R_cand"
            return "eye_pair"
        if bri < 120:
            return "eye_dark"
        return "eye_part"
    # bangs / top hair
    if cy < 520 and area > 80000:
        return "hair_front"
    if cy < 400 and 20000 < area < 200000:
        return "bangs"
    if cy < 280 and area > 50000:
        return "hair_top_acc"
    # side hair / braid
    if 200 < cy < 900 and area > 200000 and (cx < 850 or cx > 1200):
        return "hair_side"
    if 150 < cy < 850 and 100000 < area < 700000 and h > 400:
        return "hair_big"
    # body
    if cy > 900 and area > 150000:
        if bri < 100:
            return "body_dark"
        return "body_light"
    if cy > 1200 and area > 80000:
        return "legs_or_skirt"
    if 750 < cy < 1000 and area > 80000 and bri < 120:
        return "dress"
    if 40 < cy < 250 and area > 40000:
        return "wing_or_horn"
    if area > 400000 and cy < 1000:
        return "base_big"
    return "misc"


for s in all_s:
    s["guess"] = guess(s)

# print ranked
for s in sorted(all_s, key=lambda x: (x["guess"], x["cy"])):
    print(
        f"{s['guess']:14s} cy={s['cy']:6.0f} cx={s['cx']:6.0f} "
        f"{s['w']:4d}x{s['h']:4d} a={s['area']:7d} bri={s['bri']:5.0f} "
        f"{s['key']}"
    )

# labeled sheet: each layer on black with guess
cols = 5
thumb = 280
n = len(all_s)
rn = (n + cols - 1) // cols
sheet = Image.new("RGB", (cols * (thumb + 10) + 10, rn * (thumb + 48) + 10), (18, 16, 28))
draw = ImageDraw.Draw(sheet)
try:
    font = ImageFont.truetype("C:/Windows/Fonts/msjh.ttc", 13)
except Exception:
    font = ImageFont.load_default()

for i, s in enumerate(all_s):
    img = Image.open(ROOT / s["file"]).convert("RGBA")
    sc = min(thumb / img.width, thumb / img.height, 1.0)
    t = img.resize((max(1, int(img.width * sc)), max(1, int(img.height * sc))), Image.Resampling.LANCZOS)
    cx = 10 + (i % cols) * (thumb + 10)
    cy = 10 + (i // cols) * (thumb + 48)
    cell = Image.new("RGBA", (thumb, thumb), (0, 0, 0, 255))
    cell.alpha_composite(t, ((thumb - t.width) // 2, (thumb - t.height) // 2))
    sheet.paste(cell.convert("RGB"), (cx, cy))
    draw.text((cx, cy + thumb + 2), f"{i} {s['guess']}", fill=(255, 220, 120), font=font)
    draw.text((cx, cy + thumb + 18), s["key"][-32:], fill=(180, 170, 200), font=font)
    # also save solo labeled preview
    solo = Image.new("RGBA", (psd_w := 512, 512), (0, 0, 0, 255))
    full = Image.open(ROOT / s["full"]).convert("RGBA").resize((512, 512), Image.Resampling.LANCZOS)
    solo.alpha_composite(full)
    d = ImageDraw.Draw(solo)
    d.text((8, 8), f"{i}:{s['guess']}", fill=(255, 230, 100, 255), font=font)
    d.text((8, 28), s["key"][-40:], fill=(200, 200, 220, 255), font=font)
    solo.save(OUT / f"{i:02d}_{s['guess']}.png")

sheet.save(ROOT / "__labeled_sheet.png")
(ROOT / "classify.json").write_text(json.dumps(all_s, ensure_ascii=False, indent=2), encoding="utf-8")
print("wrote", ROOT / "__labeled_sheet.png", "and", OUT)
