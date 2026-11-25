# -*- coding: utf-8 -*-
"""拆件 PSD（未命名的作品 62）的類 Live2D：眼睛看游標、髮絲彈簧擺動。"""
from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageFilter, ImageTk
import tkinter as tk

ROOT = Path(__file__).resolve().parent
ART = ROOT / "assets" / "psd_import" / "untitled62"
SIZE = 680  # 顯示邊長（來源 2048）
SRC = 2048
SCALE = SIZE / SRC

# 髮絲：anchor 是 2048 座標上的擺動支點（越下面晃越大）
HAIR = {
    "49_圖層_55": (40, 0.85),  # 頭上小翅膀
    "23_新群組/00_圖層_4": (180, 0.6),
    "20_新群組/00_圖層_15": (190, 0.75),
    "21_新群組/00_新群組/00_新群組/00_新群組/00_圖層_2": (180, 0.8),
    "12_圖層_47": (160, 0.4),
    "09_圖層_50": (280, 1.0),
    "19_圖層_45": (220, 1.05),  # 臉側長髮
    "04_圖層_65": (620, 0.95),  # 雙馬尾
    "02_圖層_67": (400, 1.25),  # 細髮絲
    "01_圖層_66": (700, 1.35),  # 垂到身側的長捲髮
}
# 白頭髮蓋住了臉，眼睛要改畫在這層前面才看得到
FACE_CAP = "11_圖層_48"
# 跟著游標移動的眼睛零件（係數是看的幅度）
LOOK_PARTS = {
    "25_圖層_19": 0.85,  # 圓眼睛
    "29_圖層_24": 1.0,  # 眼珠
    "37_圖層_22": 1.25,
    "38_圖層_20": 1.25,
    "39_圖層_23": 1.35,
    "43_圖層_42": 1.35,
}
# 眼眶／眼皮，跟著眼睛一起拉到臉前面，但不跟著看
EYE_SHELL = ("27_圖層_30", "35_圖層_22", "34_圖層_21", "26_圖層_35", "40_圖層_32", "41_圖層_33")
LOOK_MAX = (16, 10)
HAIR_MAX = 34


def _over(base: Image.Image | None, layer: Image.Image) -> Image.Image:
    if base is None:
        return layer.copy()
    return Image.alpha_composite(base, layer)


def _load_resized(full_name: str) -> Image.Image:
    im = Image.open(ART / full_name).convert("RGBA")
    if im.size != (SRC, SRC):
        canvas = Image.new("RGBA", (SRC, SRC), (0, 0, 0, 0))
        canvas.paste(im, (0, 0), im)
        im = canvas
    return im.resize((SIZE, SIZE), Image.Resampling.BILINEAR)


def _shift_rows(im: Image.Image, dx_per_row: np.ndarray) -> Image.Image:
    arr = np.asarray(im)
    h, w, _ = arr.shape
    out = np.zeros_like(arr)
    dxs = dx_per_row.astype(np.int32)
    for dx in np.unique(dxs):
        rows = dxs == dx
        d = int(dx)
        if d == 0:
            out[rows] = arr[rows]
        elif d > 0:
            out[rows, d:] = arr[rows, : w - d]
        else:
            out[rows, : w + d] = arr[rows, -d:]
    return Image.fromarray(out)


def _shift(im: Image.Image, dx: float, dy: float) -> Image.Image:
    if abs(dx) < 0.2 and abs(dy) < 0.2:
        return im
    return im.transform(
        im.size, Image.AFFINE, (1, 0, -dx, 0, 1, -dy), resample=Image.Resampling.BILINEAR
    )


class Spring:
    def __init__(self, k, d):
        self.k, self.d, self.x, self.v = k, d, 0.0, 0.0

    def step(self, target, dt):
        self.v += (self.k * (target - self.x) - self.d * self.v) * dt
        self.x += self.v * dt
        return self.x


EYE_ALL = set(LOOK_PARTS) | set(EYE_SHELL)


def _dilate(im: Image.Image, times: int = 3) -> Image.Image:
    mask = im.getchannel("A")
    for _ in range(times):
        mask = mask.filter(ImageFilter.MaxFilter(7))
    return mask


class Model:
    def __init__(self, pieces):
        self.pieces = pieces

    @classmethod
    def load(cls) -> "Model":
        meta = json.loads((ART / "layers.json").read_text(encoding="utf-8"))
        layers = [r for r in meta if r.get("nonempty")]
        by_key = {r["key"]: r for r in layers}
        eyes = {k: _load_resized(by_key[k]["full"]) for k in EYE_ALL if k in by_key}
        socket = _dilate(eyes["27_圖層_30"]) if "27_圖層_30" in eyes else None

        def eye_pieces():
            out = []
            for key in EYE_SHELL:
                if key in eyes:
                    out.append(("eye", eyes[key], 0.0, None))
            for key, mul in LOOK_PARTS.items():
                if key not in eyes:
                    continue
                # 圓眼睛整顆跟著看；眼珠則留在眼眶裡
                mask = None if key == "25_圖層_19" else socket
                out.append(("eye", eyes[key], mul, mask))
            return out

        pieces = []
        buf = None
        injected = False
        for rec in reversed(layers):  # 底層先畫
            key = rec["key"]
            if key in EYE_ALL:
                continue
            im = _load_resized(rec["full"])
            if key in HAIR:
                if buf is not None:
                    pieces.append(("flat", buf))
                    buf = None
                anchor, gain = HAIR[key]
                pieces.append(("hair", im, anchor * SCALE, gain))
            else:
                buf = _over(buf, im)
            if key == FACE_CAP and not injected:
                if buf is not None:
                    pieces.append(("flat", buf))
                    buf = None
                pieces.extend(eye_pieces())
                injected = True
        if buf is not None:
            pieces.append(("flat", buf))
        if not injected:
            pieces.extend(eye_pieces())
        return cls(pieces)

    def render(self, sway: float, look: tuple[float, float]) -> Image.Image:
        sway = max(-HAIR_MAX, min(HAIR_MAX, sway))
        lx = max(-LOOK_MAX[0], min(LOOK_MAX[0], look[0]))
        ly = max(-LOOK_MAX[1], min(LOOK_MAX[1], look[1]))
        frame = None
        for kind, *rest in self.pieces:
            if kind == "flat":
                frame = _over(frame, rest[0])
            elif kind == "hair":
                im, anchor, gain = rest
                ys = np.arange(im.size[1], dtype=np.float32)
                fall = np.clip((ys - anchor) / 260.0, 0, 1) ** 1.1
                dx = np.rint(sway * gain * fall).astype(np.int32)
                frame = _over(frame, _shift_rows(im, dx))
            else:
                im, mul, mask = rest
                moved = _shift(im, lx * mul, ly * mul) if mul else im
                if mask is not None:
                    r, g, b, a = moved.split()
                    a = ImageChops.multiply(a, mask)
                    moved = Image.merge("RGBA", (r, g, b, a))
                frame = _over(frame, moved)
        if frame is None:
            frame = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
        return frame


def _on_key(rgba: Image.Image) -> Image.Image:
    """完全透明的地方才挖空，避免邊緣被透明色染成粉邊。"""
    arr = np.asarray(rgba)
    rgb = arr[:, :, :3].copy()
    hole = arr[:, :, 3] < 140
    rgb[hole] = (255, 0, 246)
    return Image.fromarray(rgb, "RGB")


def save_shots(model: Model) -> None:
    rest = model.render(0, (0, 0))
    moved = model.render(22, (14, -8))
    out = ART / "preview"
    out.mkdir(exist_ok=True)
    rest.save(out / "rest.png")
    moved.save(out / "sway_look.png")
    # 眼睛近裁，方便確認瞳孔有位移
    box = (180, 80, 500, 280)
    rest.crop(box).save(out / "eyes_rest.png")
    moved.crop(box).save(out / "eyes_look.png")
    print("shots", out)


class App:
    def __init__(self, model: Model):
        self.model = model
        self.hair = Spring(7.5, 3.2)
        self.lx = Spring(16, 7)
        self.ly = Spring(16, 7)
        self.t_prev = time.perf_counter()
        self.t0 = self.t_prev
        self.last_mx = None
        self.photo = None

        self.root = tk.Tk()
        self.root.title("拆件 L2D")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.configure(bg="#ff00f6")
        self.root.attributes("-transparentcolor", "#ff00f6")
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        self.root.geometry(f"{SIZE}x{SIZE}+{(sw - SIZE) // 2}+{(sh - SIZE) // 3}")

        self.label = tk.Label(self.root, bd=0, bg="#ff00f6")
        self.label.pack()
        self.label.bind("<ButtonPress-1>", self._down)
        self.label.bind("<B1-Motion>", self._drag)
        self.label.bind("<Button-3>", lambda e: self.root.destroy())
        self.root.bind("<Escape>", lambda e: self.root.destroy())
        self._drag_at = (0, 0)
        self._tick()

    def _down(self, e):
        self._drag_at = (e.x, e.y)

    def _drag(self, e):
        x = self.root.winfo_x() + e.x - self._drag_at[0]
        y = self.root.winfo_y() + e.y - self._drag_at[1]
        self.root.geometry(f"+{x}+{y}")

    def _tick(self):
        now = time.perf_counter()
        dt = min(0.05, now - self.t_prev)
        self.t_prev = now
        elapsed = now - self.t0
        px, py = self.root.winfo_pointerxy()
        wx, wy = self.root.winfo_rootx(), self.root.winfo_rooty()
        mx, my = px - wx, py - wy
        if self.last_mx is None:
            vx = 0.0
        else:
            vx = (mx - self.last_mx) / max(dt, 1e-3)
        self.last_mx = mx
        face_x, face_y = SIZE * 0.50, SIZE * 0.30
        tx = max(-1.0, min(1.0, (mx - face_x) / (SIZE * 0.45)))
        ty = max(-1.0, min(1.0, (my - face_y) / (SIZE * 0.45)))
        idle = math.sin(elapsed * 1.3) * 12 + math.sin(elapsed * 0.37) * 4
        sway = self.hair.step(max(-HAIR_MAX, min(HAIR_MAX, -vx * 0.02 + idle)), dt)
        look = (
            self.lx.step(tx * LOOK_MAX[0], dt),
            self.ly.step(ty * LOOK_MAX[1] + math.sin(elapsed * 0.8) * 1.2, dt),
        )
        bob = int(round(math.sin(elapsed * 1.6) * 2))
        frame = self.model.render(sway, look)
        if bob:
            shifted = Image.new("RGBA", frame.size, (0, 0, 0, 0))
            shifted.paste(frame, (0, bob), frame)
            frame = shifted
        rgb = _on_key(frame)
        self.photo = ImageTk.PhotoImage(rgb)
        self.label.configure(image=self.photo)
        self.root.after(33, self._tick)

    def run(self):
        self.root.mainloop()


def main():
    model = Model.load()
    if "--shot" in sys.argv:
        save_shots(model)
        return
    App(model).run()


if __name__ == "__main__":
    main()
