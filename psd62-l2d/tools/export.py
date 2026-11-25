# -*- coding: utf-8 -*-
"""把「未命名的作品 (62).psd」整理成 L2D 素材。

輸出：
  web/parts.js              網頁版 L2D（web/index.html）用的零件
  cubism/psd62_cubism.psd   給 Live2D Cubism Editor 匯入的整理版 PSD

整理內容：
  - 依 PSD 圖層順序拆出零件，套上部位名稱與綁定角色
  - 補圖：被上層蓋住、本身沒上色的地方用鄰近顏色補滿，動起來不會露出空洞
  - 清掉離群的多餘筆畫
  - 頭髮高光層裡的眼睛反光拆成獨立零件
  - 脖子移到後腦勺之上（原本被後腦勺蓋住）
  - Cubism 版另外：剪切遮罩先烘焙、左右成對部位拆成 _L/_R、依部位分群組、
    附上隱藏參考層「張嘴」「閉眼（上眼皮翻轉）」

用法：python tools/export.py [PSD 路徑]
"""
from __future__ import annotations

import base64
import io
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from psd_tools import PSDImage
from psd_tools.api.layers import Group, PixelLayer
from psd_tools.constants import BlendMode
from scipy import ndimage as ndi

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PSD = Path.home() / "Downloads" / "未命名的作品 (62).psd"
WEB = ROOT / "web" / "parts.js"
CUBISM = ROOT / "cubism" / "psd62_cubism.psd"

# PSD 圖層序號（底→頂，只算非群組圖層）→ (部位名稱, 綁定角色)
PARTS = {
    1: ("後髮尾", "tails"), 2: ("後髮尾線", "tails"), 4: ("辮子", "braid"), 5: ("脖子", "neck"),
    6: ("緞帶尾", "ribbon"), 7: ("緞帶A", "ribbon"), 8: ("緞帶B", "ribbon"),
    9: ("側髮髻", "head"), 11: ("後腦勺", "head"), 12: ("耳朵", "ear"),
    13: ("臉", "face"), 14: ("腮紅", "face"), 15: ("臉上髮影", "hair"), 16: ("嘴", "mouth"), 17: ("臉線", "face"),
    19: ("側髮", "hair"), 20: ("內側髮", "hair"), 21: ("髮弧", "hair"), 22: ("髮弧陰影", "hair"), 23: ("頭髮線", "hair"),
    24: ("瀏海", "hair"), 25: ("瀏海陰影", "hair"), 26: ("瀏海線", "hair"), 27: ("頭髮高光", "hair"),
    28: ("眉毛", "brow"), 29: ("雙眼皮線", "crease"),  # 額頭上的兩個圓是麻呂眉
    30: ("眼白", "sclera"), 31: ("眼白陰影", "sclera"), 32: ("虹膜底", "iris"), 33: ("虹膜外圈", "iris"),
    34: ("瞳孔", "iris"), 35: ("虹膜高光A", "iris"), 36: ("虹膜高光B", "iris"), 37: ("虹膜外框", "iris"),
    38: ("上眼皮", "lid"), 39: ("眼皮高光", "lid"), 40: ("上睫毛A", "lid"), 41: ("上睫毛B", "lid"),
    42: ("眼皮高光點", "sclera"), 43: ("眼角睫毛", "lid"), 44: ("下眼皮", "lowlid"), 45: ("下睫毛", "lowlid"),
    46: ("眼睛反光", "iris"),
    47: ("袖子", "arms"), 48: ("外裙", "skirt"), 49: ("腿", "legs"), 50: ("洋裝", "dress"), 51: ("領子", "collar"),
    52: ("頭上翅膀", "wings"), 54: ("領結尾", "bow"), 55: ("領結", "bow"), 56: ("領結結", "bow"),
}
DRAW_AFTER = {5: 11}  # 脖子畫在後腦勺之上
SPLITS = {271: (27, "眼睛反光(髮高光層)", "sclera", (560, 2048))}
CLEANUP = {  # 只保留框內 (x0, y0, x1, y1)
    2: (500, 600, 1550, 1300),   # 後髮尾線：左右兩側多餘的弧線
    9: (0, 0, 2048, 1300),       # 側髮髻：裙子附近的雜線
    12: (0, 0, 2048, 800),       # 耳朵：下方雜點
    17: (0, 0, 2048, 1000),      # 臉線：洋裝上的雜線
    45: (760, 0, 1290, 760),     # 下睫毛：雜點
}
FILL_GENERIC = [1, 4, 6, 7, 8, 9, 11, 12, 13, 19, 20, 21, 24, 47, 48, 49, 50, 51, 54, 55]
FILL_EXTRA = {
    5: [[(976, 690), (1072, 690), (1084, 905), (964, 905)]],  # 脖子往上下延伸
    49: [[(842, 1170), (1206, 1170), (1206, 1340), (842, 1340)]],  # 腿往上延伸到裙子裡
}
FILL_HULL = {48: 50}  # 外裙：補滿左右兩片中間，只補在洋裝底下

# ---- Cubism 版 ----
SPLIT_LR = {1, 2, 4, 6, 7, 8, 9, 12, 14, 19, 20, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43,
            44, 45, 46, 271, 47, 48, 49, 52}
GROUPS = [  # (群組名稱, 零件 id)；同一群組內維持原本的前後順序
    ("後髮", [1, 2, 4, 6, 7, 8, 9, 11]),
    ("脖子", [5]),
    ("臉", [12, 13, 14, 15, 16, 1001, 17]),
    ("前髮", [19, 20, 21, 22, 23, 24, 25, 26, 27]),
    ("眼睛_L", [271, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 2001]),
    ("眼睛_R", [271, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 2001]),
    ("身體", [47, 48, 49, 50, 51, 54, 55, 56]),
    ("頭上翅膀", [52]),
]
LID_C0, LID_CLOSED = 618, 640  # 閉眼參考：上眼皮以 y=LID_C0 為軸翻轉，落在 LID_CLOSED
MOUTH = (1024, 726)


def layer_list(psd: PSDImage):
    out = []

    def walk(group):
        for layer in group:
            if layer.is_group():
                walk(layer)
                continue
            im = layer.topil()
            if im is None:
                continue
            canvas = Image.new("RGBA", (psd.width, psd.height), (0, 0, 0, 0))
            canvas.paste(im.convert("RGBA"), (layer.left, layer.top))
            out.append((layer, np.asarray(canvas).copy()))

    walk(psd)
    return out


def nearest_fill(rgba: np.ndarray, region: np.ndarray) -> None:
    src = rgba[..., 3] > 200
    if not src.any() or not region.any():
        return
    _, (iy, ix) = ndi.distance_transform_edt(~src, return_indices=True)
    col = rgba[iy, ix, :3].astype(np.float32)
    for c in range(3):
        col[..., c] = ndi.uniform_filter(col[..., c], 5)
    rgba[region, :3] = col[region].astype(np.uint8)
    rgba[region, 3] = 255


def poly_mask(shape, polys):
    m = Image.new("L", (shape[1], shape[0]), 0)
    d = ImageDraw.Draw(m)
    for p in polys:
        d.polygon(p, fill=255)
    return np.asarray(m) > 0


def hull_mask(a: np.ndarray) -> np.ndarray:
    ys, xs = np.nonzero(a)
    pts = np.stack([xs, ys], 1)
    pts = pts[np.lexsort((pts[:, 1], pts[:, 0]))][:: max(1, len(pts) // 20000)]

    def cross(o, a_, b):
        return (a_[0] - o[0]) * (b[1] - o[1]) - (a_[1] - o[1]) * (b[0] - o[0])

    lower, upper = [], []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(tuple(p))
    for p in pts[::-1]:
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(tuple(p))
    return poly_mask(a.shape, [lower[:-1] + upper[:-1]])


def mouth_sprite() -> Image.Image:
    """張嘴圖（淺色，與網頁版相同），4 倍超取樣。"""
    k = 4
    im = Image.new("RGBA", (104 * k, 76 * k), (0, 0, 0, 0))
    box = (8 * k, 6 * k, 96 * k, 70 * k)
    ImageDraw.Draw(im).ellipse(box, fill=(215, 160, 170, 255))
    mask = Image.new("L", im.size, 0)
    ImageDraw.Draw(mask).ellipse(box, fill=255)
    inner = Image.new("RGBA", im.size, (0, 0, 0, 0))
    di = ImageDraw.Draw(inner)
    di.ellipse((18 * k, 50 * k, 86 * k, 94 * k), fill=(244, 198, 205, 255))
    di.polygon([(30 * k, 8 * k), (38 * k, 22 * k), (44 * k, 8 * k)], fill=(255, 255, 255, 255))
    di.polygon([(60 * k, 8 * k), (66 * k, 22 * k), (74 * k, 8 * k)], fill=(255, 255, 255, 255))
    a = np.minimum(np.asarray(inner.getchannel("A")), np.asarray(mask))
    im.paste(inner, (0, 0), Image.fromarray(a))
    ImageDraw.Draw(im).ellipse(box, outline=(185, 135, 144, 255), width=5 * k)
    return im.resize((52, 38), Image.LANCZOS)


def build_items(psd: PSDImage):
    layers = layer_list(psd)
    items = []
    for idx, (layer, arr) in enumerate(layers):
        if idx not in PARTS:
            continue
        if idx in CLEANUP:
            x0, y0, x1, y1 = CLEANUP[idx]
            keep = np.zeros(arr.shape[:2], bool)
            keep[y0:y1, x0:x1] = True
            arr[~keep] = 0
        if not (arr[..., 3] > 3).any():
            continue
        name, role = PARTS[idx]
        blend = "screen" if "SCREEN" in str(layer.blend_mode) else "normal"
        items.append(dict(id=idx, name=name, role=role, blend=blend, clip=bool(layer.clipping), arr=arr))
    for nid, (sid, name, role, (y0, y1)) in SPLITS.items():
        src = next(i for i in items if i["id"] == sid)
        part = np.zeros_like(src["arr"])
        part[y0:y1] = src["arr"][y0:y1]
        src["arr"][y0:y1] = 0
        items.insert(items.index(src) + 1, dict(id=nid, name=name, role=role, blend=src["blend"], clip=False, arr=part))
    for pid, after in DRAW_AFTER.items():
        it = next(i for i in items if i["id"] == pid)
        items.remove(it)
        items.insert(items.index(next(i for i in items if i["id"] == after)) + 1, it)
    # 補圖：只補被上層（不透明）蓋住的地方 → 靜止時畫面不變
    # 剪切圖層不算遮蔽（它只顯示在底圖範圍內，補了底圖反而會讓它透出來）
    opaque = [(i["arr"][..., 3] > 200) & (not i["clip"]) for i in items]
    for k, it in enumerate(items):
        pid = it["id"]
        if pid not in FILL_GENERIC and pid not in FILL_EXTRA and pid not in FILL_HULL:
            continue
        above = np.zeros(opaque[0].shape, bool)
        for m in opaque[k + 1:]:
            above |= m
        above = ndi.binary_erosion(above, iterations=2)
        a = it["arr"][..., 3] > 40
        region = np.zeros_like(a)
        if pid in FILL_GENERIC:
            region |= ndi.binary_fill_holes(a) | ndi.binary_closing(a, structure=np.ones((41, 41)))
        if pid in FILL_EXTRA:
            region |= poly_mask(a.shape, FILL_EXTRA[pid])
        region &= ~a & above
        if pid in FILL_HULL:
            cover = next(i for i in items if i["id"] == FILL_HULL[pid])["arr"][..., 3] > 200
            region |= hull_mask(a) & ~a & ndi.binary_erosion(cover, iterations=6)
        nearest_fill(it["arr"], region)
        print(f"  補圖 #{pid} {it['name']}: {int(region.sum())} px")
    return items


def crop(arr, pad=4):
    ys, xs = np.nonzero(arr[..., 3] > 3)
    h, w = arr.shape[:2]
    x0, y0 = max(0, xs.min() - pad), max(0, ys.min() - pad)
    x1, y1 = min(w, xs.max() + pad + 1), min(h, ys.max() + pad + 1)
    return int(x0), int(y0), int(x1), int(y1)


def write_web(items):
    web = []
    for it in items:
        x0, y0, x1, y1 = crop(it["arr"])
        buf = io.BytesIO()
        Image.fromarray(it["arr"][y0:y1, x0:x1], "RGBA").save(buf, "PNG", optimize=True)
        web.append(dict(id=it["id"], name=it["name"], role=it["role"], blend=it["blend"], clip=it["clip"],
                        x=x0, y=y0, w=x1 - x0, h=y1 - y0,
                        src="data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()))
    WEB.parent.mkdir(parents=True, exist_ok=True)
    WEB.write_text("window.PARTS=" + json.dumps(web, ensure_ascii=False) + ";", encoding="utf-8")
    print("web ->", WEB)


def write_cubism(items, size):
    W, H = size
    by_id = {}
    # 剪切遮罩烘焙：剪切圖層的 alpha 乘上底圖 alpha
    base = None
    for it in items:
        arr = it["arr"].copy()
        if it["clip"] and base is not None:
            arr[..., 3] = (arr[..., 3].astype(np.uint16) * base[..., 3] // 255).astype(np.uint8)
        else:
            base = it["arr"]
        by_id[it["id"]] = dict(it, arr=arr)
    # 張嘴（參考，隱藏）
    m = np.zeros((H, W, 4), np.uint8)
    spr = np.asarray(mouth_sprite())
    mx, my = MOUTH[0] - 26, MOUTH[1] - 19
    m[my:my + spr.shape[0], mx:mx + spr.shape[1]] = spr
    by_id[1001] = dict(id=1001, name="張嘴(參考)", role="mouthOpen", blend="normal", arr=m, hidden=True)
    # 閉眼（參考，隱藏）：上眼皮相關圖層合成後以 y=LID_C0 為軸翻轉
    lid = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    for pid in (38, 39, 40, 41, 43):
        lid.alpha_composite(Image.fromarray(by_id[pid]["arr"]))
    lid = np.asarray(lid)
    closed = np.zeros_like(lid)
    c = LID_C0 + LID_CLOSED
    ys = np.arange(H)
    src_rows = c - ys
    ok = (src_rows >= 0) & (src_rows < H)
    closed[ys[ok]] = lid[src_rows[ok]]
    by_id[2001] = dict(id=2001, name="閉眼(上眼皮翻轉,參考)", role="lid", blend="normal", arr=closed, hidden=True)

    psd = PSDImage.new("RGB", (W, H), depth=8)
    for gname, ids in GROUPS:
        side = gname[-1] if gname.endswith(("_L", "_R")) else None
        layers = []
        for pid in ids:
            it = by_id.get(pid)
            if it is None:
                continue
            arr = it["arr"]
            if pid in SPLIT_LR or pid in (2001,):
                halves = {"L": arr.copy(), "R": arr.copy()}
                halves["L"][:, 1024:] = 0
                halves["R"][:, :1024] = 0
                pieces = [(f"{it['name']}_{s}", halves[s]) for s in ("L", "R") if side in (None, s)]
            elif side is not None:
                continue
            else:
                pieces = [(it["name"], arr)]
            for name, a in pieces:
                if not (a[..., 3] > 3).any():
                    continue
                layers.append((name, a, it["blend"], it.get("hidden", False)))
        if not layers:
            continue
        # 中文名稱：先用英數名建立，再透過 .name 寫入 Unicode 圖層名稱
        group = Group.new(psd, name="group")
        group.name = gname
        for name, a, blend, hidden in layers:  # 先加的在下面
            x0, y0, x1, y1 = crop(a, pad=0)
            lyr = PixelLayer.frompil(Image.fromarray(a[y0:y1, x0:x1], "RGBA"), group, name="layer", top=y0, left=x0)
            lyr.name = name
            if blend == "screen":
                lyr.blend_mode = BlendMode.SCREEN
            if hidden:
                lyr.visible = False
    CUBISM.parent.mkdir(parents=True, exist_ok=True)
    psd.save(CUBISM)
    print("cubism ->", CUBISM)


def main():
    psd_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PSD
    psd = PSDImage.open(psd_path)
    items = build_items(psd)
    write_web(items)
    write_cubism(items, (psd.width, psd.height))


if __name__ == "__main__":
    main()
