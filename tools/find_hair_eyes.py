# -*- coding: utf-8 -*-
"""Find which layers own the long side locks, and whether a face sits under the hair."""
import json
from pathlib import Path

import numpy as np
from PIL import Image

ART = Path(r"d:\CODE\dream-god-desktop-pet\assets\psd_import\untitled62")
meta = [r for r in json.loads((ART / "layers.json").read_text(encoding="utf-8")) if r.get("nonempty")]

# long locks sit roughly x 150-450 and 1600-1900, y 700-1400 on 2048 canvas
# sample at 512 for speed
S = 512
sc = S / 2048


def load(rec):
    im = Image.open(ART / rec["full"]).convert("RGBA").resize((S, S), Image.Resampling.BOX)
    return np.asarray(im)


lock = np.zeros((S, S), bool)
# side bands
lock[:, : int(0.28 * S)] = True
lock[:, int(0.72 * S) :] = True
lock[: int(0.28 * S), :] = False
lock[int(0.78 * S) :, :] = False

print("--- pixels in side-lock region ---")
owners = []
for rec in meta:
    a = load(rec)
    m = a[:, :, 3] > 20
    n = int((m & lock).sum())
    if n > 30:
        owners.append((n, rec["key"], a[m][:, :3].mean() if m.any() else 0))
        print(f"{n:6d}  bri={a[m,:3].mean():5.0f}  {rec['key']}")

# head disk coverage
print("--- head disk coverage ---")
yy, xx = np.mgrid[0:S, 0:S]
disk = (xx - S * 0.5) ** 2 + (yy - S * 0.28) ** 2 < (S * 0.16) ** 2
for rec in meta:
    a = load(rec)
    m = a[:, :, 3] > 20
    cov = (m & disk).sum() / disk.sum()
    if cov > 0.05:
        print(f"cov={cov:.2f} bri={a[m,:3].mean():5.0f} {rec['key']}")

# composite without the biggest head-covering pale layers
hide = set()
for rec in meta:
    a = load(rec)
    m = a[:, :, 3] > 20
    cov = (m & disk).sum() / max(disk.sum(), 1)
    if cov > 0.25:
        hide.add(rec["key"])
        print("HIDE", rec["key"])

canvas = Image.new("RGBA", (S, S), (0, 0, 0, 255))
for rec in reversed(meta):  # back to front? meta is top-first, so reverse
    if rec["key"] in hide:
        continue
    im = Image.open(ART / rec["full"]).convert("RGBA").resize((S, S), Image.Resampling.BILINEAR)
    canvas = Image.alpha_composite(canvas, im)
canvas.convert("RGB").save(ART / "preview" / "without_headcap.png")
print("wrote without_headcap, hid", hide)
