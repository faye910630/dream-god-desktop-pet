# -*- coding: utf-8 -*-
"""Build progressive composites to discover draw order & useful parts."""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(r"d:\CODE\dream-god-desktop-pet\assets\psd_import\untitled62")
meta = [r for r in json.loads((ROOT / "layers.json").read_text(encoding="utf-8")) if r.get("nonempty")]
# PSD stack: first in list is TOP. Reverse for bottom-up paint.
order = list(reversed(meta))

font = ImageFont.truetype("C:/Windows/Fonts/msjh.ttc", 16)
canvas = Image.new("RGBA", (2048, 2048), (0, 0, 0, 255))
prev = ROOT / "stack_steps"
prev.mkdir(exist_ok=True)

# Also emit a strip of every layer alone on composite for ID
for i, r in enumerate(order):
    layer = Image.open(ROOT / r["full"]).convert("RGBA")
    canvas = Image.alpha_composite(canvas, layer)
    if i % 5 == 0 or i == len(order) - 1:
        small = canvas.resize((400, 400), Image.Resampling.LANCZOS).convert("RGB")
        d = ImageDraw.Draw(small)
        d.text((6, 6), f"after {i}: {r['name']}", fill=(255, 220, 80), font=font)
        small.save(prev / f"step_{i:02d}.png")

canvas.resize((700, 700), Image.Resampling.LANCZOS).save(ROOT / "__stack_full.png")

# Solo important candidates on black for eyes/hair region crop
crop_box = (600, 150, 1450, 900)  # head region
for i, r in enumerate(meta):
    full = Image.open(ROOT / r["full"]).convert("RGBA")
    a = full.split()[-1]
    if a.getbbox() is None:
        continue
    head = full.crop(crop_box)
    if head.split()[-1].getbbox() is None:
        continue
    bg = Image.new("RGBA", head.size, (0, 0, 0, 255))
    bg.alpha_composite(head)
    out = bg.convert("RGB")
    d = ImageDraw.Draw(out)
    d.text((4, 4), f"{i} {r['key'][-30:]}", fill=(255, 230, 100), font=font)
    out.save(ROOT / "labeled" / f"head_{i:02d}.png")

print("steps", len(list(prev.glob('*.png'))), "head previews written")
