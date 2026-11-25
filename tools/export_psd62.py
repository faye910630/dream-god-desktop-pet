# -*- coding: utf-8 -*-
from pathlib import Path
from psd_tools import PSDImage
from PIL import Image
import json

src = Path(r"c:\Users\dear9\Downloads\未命名的作品 (62).psd")
out = Path(r"d:\CODE\dream-god-desktop-pet\assets\psd_import\untitled62")
out.mkdir(parents=True, exist_ok=True)
psd = PSDImage.open(src)
print("canvas", psd.width, psd.height)


def walk(layers, prefix="", depth=0):
    rows = []
    for i, layer in enumerate(layers):
        name = layer.name or f"unnamed_{i}"
        kind = layer.kind
        visible = layer.visible
        bbox = getattr(layer, "bbox", None)
        print("  " * depth + f"[{kind}] {name} vis={visible} bbox={bbox}")
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)[:40]
        path_key = f"{prefix}{i:02d}_{safe}"
        if kind == "group":
            rows.append(
                {
                    "key": path_key,
                    "name": name,
                    "kind": kind,
                    "visible": visible,
                    "bbox": list(bbox) if bbox else None,
                    "children": True,
                }
            )
            rows.extend(walk(list(layer), prefix=path_key + "/", depth=depth + 1))
            continue
        try:
            img = layer.composite()
        except Exception as e:
            img = None
            print("  " * depth + f"  composite fail: {e}")
        if img is None:
            rows.append(
                {
                    "key": path_key,
                    "name": name,
                    "kind": kind,
                    "visible": visible,
                    "bbox": list(bbox) if bbox else None,
                    "nonempty": False,
                }
            )
            continue
        left, top, right, bottom = layer.bbox
        full = Image.new("RGBA", (psd.width, psd.height), (0, 0, 0, 0))
        rgba = img.convert("RGBA")
        if rgba.size == (psd.width, psd.height):
            full = rgba
        elif rgba.size == (max(0, right - left), max(0, bottom - top)):
            full.paste(rgba, (left, top), rgba)
        else:
            full.paste(rgba, (left, top), rgba)
        box = full.split()[-1].getbbox()
        crop = full.crop(box) if box else full
        fname = path_key.replace("/", "__") + ".png"
        full_name = path_key.replace("/", "__") + "__full.png"
        crop.save(out / fname)
        full.save(out / full_name)
        rows.append(
            {
                "key": path_key,
                "name": name,
                "kind": kind,
                "visible": visible,
                "bbox": [left, top, right, bottom],
                "content_bbox": list(box) if box else None,
                "file": fname,
                "full": full_name,
                "nonempty": bool(box),
            }
        )
    return rows


meta = walk(list(psd))
(out / "layers.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
psd.composite().convert("RGBA").save(out / "__composite.png")
print("exported", len(meta), "nonempty", sum(1 for r in meta if r.get("nonempty")))
print("out", out)
