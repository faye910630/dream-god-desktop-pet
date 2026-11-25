# -*- coding: utf-8 -*-
import json
from pathlib import Path
import numpy as np
from PIL import Image

ART = Path(r"d:\CODE\dream-god-desktop-pet\assets\psd_import\untitled62")
meta = [r for r in json.loads((ART / "layers.json").read_text(encoding="utf-8")) if r.get("nonempty")]
S = 512

def load(rec):
    return np.asarray(Image.open(ART / rec["full"]).convert("RGBA").resize((S, S), Image.Resampling.BOX))

yy, xx = np.mgrid[0:S, 0:S]
# long pale locks beside the dress
band = ((xx < S * 0.42) | (xx > S * 0.58)) & (yy > S * 0.32) & (yy < S * 0.72)
print("--- pale pixels in side bands ---")
for rec in meta:
    a = load(rec)
    m = (a[:, :, 3] > 20) & band
    if m.sum() < 40:
        continue
    bri = a[m][:, :3].mean()
    print(f"n={int(m.sum()):5d} bri={bri:5.0f} {rec['key']}")
