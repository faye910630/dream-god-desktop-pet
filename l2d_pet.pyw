"""
夢境神明 L2D 風格桌寵（8 視圖 + 網格變形）

- 使用 assets/six_views/l2d_psd/*_import_preview.png（由各視圖 PSD 拆件合成）當作 8 個角度
- 以類 Live2D 參數驅動網格變形：呼吸、頭部擺動、身體傾斜、頭髮／裙擺物理、腿部擺動、頭上小翅膀
- 動作：左右走路、轉身／轉圈、彈跳、前空翻、側翻、飛上螢幕頂端倒吊、拖曳甩動、拋出落地彈跳
- 視窗：Win32 UpdateLayeredWindow 逐像素半透明（邊緣不鋸齒）

執行：pythonw l2d_pet.pyw
預覽：python l2d_pet.pyw --demo out.gif   （不開視窗，輸出示範動畫）
"""

from __future__ import annotations

import json
import math
import os
import random
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageOps

ROOT = Path(__file__).resolve().parent
VIEW_DIR = ROOT / "assets" / "six_views" / "l2d_psd"
VIEW_FILES = {
    "front": "01_front_import_preview.png",
    "fl": "02_front_three_quarter_import_preview.png",  # 面向左前
    "left": "03_left_import_preview.png",
    "right": "04_right_import_preview.png",
    "bl": "05_back_three_quarter_import_preview.png",  # 背向左後
    "back": "06_back_import_preview.png",
    "top": "07_top_import_preview.png",
    "bottom": "08_bottom_import_preview.png",
}
# yaw：0 = 正面，往畫面右轉為正
YAW_VIEWS = [
    ("front", False),  # 0
    ("fl", True),  # 45  右前（鏡像左前）
    ("right", False),  # 90
    ("bl", True),  # 135 右後（鏡像左後）
    ("back", False),  # 180
    ("bl", False),  # 225 左後
    ("left", False),  # 270
    ("fl", False),  # 315 左前
]
# 前空翻：pitch 0/90/180/270 → (視圖, 額外平面旋轉)
FLIP_VIEWS = [(("front", False), 0), (("top", False), 0), (("back", False), 180), (("bottom", False), 0)]

# 顯示倍率（角色本體固定 64×64 點陣，放大用最近鄰）
SCALE = 2  # 顯示倍率固定 2 倍（64 格 → 128px）

SHOULDER_ROW = 30  # 側面圖（64 格）肩膀所在列
NECK_ROW = 28  # 正面轉頭時，頭／身體的分界列
ARM_SWING = 40.0  # 走路時手臂擺動角度
WALK_SPEED = 0.26  # 走路速度（角色高度／秒）
WALK_STEP_HZ = 1.3  # 每秒步伐循環數
WALK_STRIDE = 4.0  # 跨步（點陣格）
TRIP_CHANCE = 0.08  # 每次走路跌倒的機率
CLIMB_SPEED = 0.45  # 爬視窗速度（角色高度／秒）
ARM_PATTERN = [
    "..ooo..",
    ".o###o.",
    ".o###o.",
    ".o####o",
    "o#####o",
    "o#####o",
    "o#####o",
    "o#####o",
    ".oWWWo.",
    ".oWWWo.",
    "..oso..",
    "...o...",
]
PIXEL_DIR = ROOT / "assets" / "pixel64"
N = 64  # 角色點陣尺寸
PAD = 8  # 變形用留白
CANVAS = N + 2 * PAD
WIN_N = 112  # 原生視窗尺寸（容納旋轉／壓扁）
LINE_STRENGTH = 0.5  # 縮圖時保留深色線條（眼睛、髮絲）的強度
PALETTE_COLORS = 32
OUTLINE = (58, 52, 66, 255)

# 原圖座標（1024 畫布）中的關鍵位置
SRC = 1024
SRC_Y0, SRC_Y1 = 14, 998  # 裁切成正方形後縮成 64×64
KN = N / (SRC_Y1 - SRC_Y0)  # 每個原圖像素對應的點陣像素
CROP_HALF = 400
CENTER_Y = 512
FEET_Y = 944
HEAD_Y = 25


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def ease(p):
    return p * p * (3 - 2 * p)


def rot2(x, y, deg):
    r = math.radians(deg)
    c, s = math.cos(r), math.sin(r)
    return x * c - y * s, x * s + y * c


def wrap180(a):
    return (a + 180.0) % 360.0 - 180.0


# ------------------------------------------------------------------ rig
def _lum(c):
    return c[..., 0] * 0.299 + c[..., 1] * 0.587 + c[..., 2] * 0.114


def _downscale_keep_lines(im: Image.Image) -> np.ndarray:
    """把 1024 原圖縮成 64×64：區塊平均，但在亮區保留深色細線（眼睛、髮絲）。"""
    B = 16
    a = np.asarray(im)[:, :, 3].astype(np.float64)
    cols = a.sum(0)
    cx = int(round((cols * np.arange(cols.size)).sum() / max(cols.sum(), 1)))
    half = (SRC_Y1 - SRC_Y0) // 2
    big = im.crop((cx - half, SRC_Y0, cx + half, SRC_Y1)).resize((N * B, N * B), Image.LANCZOS)
    A = np.asarray(big).astype(np.float32) / 255
    blk = A.reshape(N, B, N, B, 4).transpose(0, 2, 1, 3, 4).reshape(N, N, B * B, 4)
    al = blk[..., 3]
    cov = al.mean(-1)
    mean = (blk[..., :3] * al[..., None]).sum(2) / np.maximum(al.sum(-1), 1e-6)[..., None]
    L = np.where(al > 0.5, _lum(blk[..., :3]), 9.0)
    idx = L.argmin(-1)
    mn = np.take_along_axis(blk[..., :3], idx[..., None, None], 2)[:, :, 0]
    contrast = np.clip((_lum(mean) - _lum(mn) - 0.12) / 0.25, 0, 1) * np.clip((_lum(mean) - 0.35) / 0.2, 0, 1)
    w = (LINE_STRENGTH * contrast)[..., None]
    out = np.zeros((N, N, 4), np.float32)
    out[..., :3] = mean * (1 - w) + mn * w
    out[..., 3] = cov
    return (out * 255).clip(0, 255).astype(np.uint8)


def build_pixel_sprites(force=False) -> dict[str, Image.Image]:
    """產生（或讀取已存在的）64×64 點陣精靈圖。assets/pixel64/*.png 可以手動逐點修改。"""
    PIXEL_DIR.mkdir(parents=True, exist_ok=True)
    paths = {k: PIXEL_DIR / f"{k}.png" for k in VIEW_FILES}
    if not force and all(p.exists() for p in paths.values()):
        return {k: Image.open(p).convert("RGBA") for k, p in paths.items()}
    raw = {k: _downscale_keep_lines(Image.open(VIEW_DIR / fn).convert("RGBA")) for k, fn in VIEW_FILES.items()}
    opaque = np.concatenate([r[:, :, :3][r[:, :, 3] > 110] for r in raw.values()])
    pal = Image.fromarray(opaque.reshape(-1, 1, 3)).quantize(PALETTE_COLORS, method=Image.MEDIANCUT)
    sprites = {}
    for k, r in raw.items():
        if not force and paths[k].exists():
            sprites[k] = Image.open(paths[k]).convert("RGBA")
            continue
        q = np.asarray(Image.fromarray(r[:, :, :3]).quantize(palette=pal, dither=Image.Dither.NONE).convert("RGB"))
        m = r[:, :, 3] > 110
        res = np.zeros((N, N, 4), np.uint8)
        res[..., :3] = q
        res[..., 3] = m * 255
        nb = np.zeros_like(m)
        nb[1:] |= m[:-1]
        nb[:-1] |= m[1:]
        nb[:, 1:] |= m[:, :-1]
        nb[:, :-1] |= m[:, 1:]
        res[nb & ~m] = OUTLINE
        sprites[k] = Image.fromarray(res)
        sprites[k].save(paths[k])
    return sprites


# ------------------------------------------------------------------ 月光花（點陣）
FLOWER_W, FLOWER_H = 23, 42
FLOWER_STAGES = [(0, "種子"), (15, "發芽"), (45, "藤葉"), (90, "花苞"), (150, "開花")]  # 種下後秒數
PLANT_CHANCE = 0.4  # 每次走路種花的機率
MAX_FLOWERS = 15

_C = {
    "o": OUTLINE,
    "L": (36, 62, 42, 255),  # 葉外框
    "G": (98, 150, 84, 255),  # 葉
    "g": (146, 192, 118, 255),  # 葉亮部
    "S": (84, 122, 66, 255),  # 莖
    "W": (246, 246, 238, 255),  # 花瓣
    "w": (222, 228, 216, 255),  # 花瓣陰影
    "y": (206, 226, 168, 255),  # 星形花脈（淡綠）
    "c": (222, 228, 130, 255),  # 花心
    "D": (92, 70, 58, 255),  # 土
    "d": (122, 96, 76, 255),  # 土亮部
}
_LEAF = [
    ".LL.LL.",
    "LGgLGGL",
    "LGgGGGL",
    ".LGGGL.",
    "..LGL..",
    "...L...",
]
_SPROUT = [
    "LL...LL",
    "LgL.LGL",
    ".LGSGL.",
    "...S...",
]
_BUD = [
    ".o.",
    "oWo",
    "owo",
    "oyo",
    "oGo",
    ".L.",
]


def _stamp(arr, pattern, x0, y0, flip=False):
    for j, row in enumerate(pattern):
        if flip:
            row = row[::-1]
        for i, ch in enumerate(row):
            if ch != ".":
                x, y = x0 + i, y0 + j
                if 0 <= x < arr.shape[1] and 0 <= y < arr.shape[0]:
                    arr[y, x] = _C[ch]


def _bloom(arr, cx, cy, open_frac=1.0):
    """正面的月光花：白色圓形花瓣＋五道淡綠星紋＋花心。"""
    R = 6.2 * open_frac
    mask = np.zeros(arr.shape[:2], bool)
    rays = [math.radians(-90 + 72 * k) for k in range(5)]
    for y in range(arr.shape[0]):
        for x in range(arr.shape[1]):
            dx, dy = x - cx, y - cy
            r = math.hypot(dx, dy)
            th = math.atan2(dy, dx)
            if r <= R * (0.93 + 0.07 * math.cos(5 * (th + math.pi / 2))):
                mask[y, x] = True
                col = _C["W"] if dy < 2.5 else _C["w"]
                for a in rays:
                    if r > 0.5 and abs(math.sin(th - a)) * r < 0.55 and math.cos(th - a) > 0:
                        col = _C["y"]
                if r < 1.3:
                    col = _C["c"]
                arr[y, x] = col
    nb = np.zeros_like(mask)
    nb[1:] |= mask[:-1]
    nb[:-1] |= mask[1:]
    nb[:, 1:] |= mask[:, :-1]
    nb[:, :-1] |= mask[:, 1:]
    arr[nb & ~mask] = _C["o"]


def draw_moonflower(stage: int, sway: int = 0, glow: float = 0.0) -> Image.Image:
    """回傳 FLOWER_W×FLOWER_H 的點陣圖。stage 0~4，sway 為頂端左右 1 格擺動，glow 0~1 夜光。"""
    W, H = FLOWER_W, FLOWER_H
    arr = np.zeros((H, W, 4), np.uint8)
    cx = W // 2
    base = H - 1
    # 土堆
    _stamp(arr, ["..DDD..", ".DdddD.", "DDDDDDD"], cx - 3, base - 2)
    if stage == 0:
        arr[base - 3, cx] = _C["d"]
        return Image.fromarray(arr)
    if stage == 1:
        _stamp(arr, _SPROUT, cx - 3, base - 6)
        return Image.fromarray(arr)
    stem_h = {2: 14, 3: 21, 4: 22}[stage]
    top = base - 2 - stem_h
    # 微彎的藤蔓莖
    for y in range(top, base - 2):
        f = (base - 2 - y) / stem_h
        x = cx + int(round(math.sin(f * 3.2) * 1.2 + sway * f * f))
        arr[y, x] = _C["S"]
    leaf_rows = {2: [6, 11], 3: [6, 12, 17], 4: [6, 12, 17]}[stage]
    for k, h in enumerate(leaf_rows):
        y = base - 2 - h
        f = h / stem_h
        x = cx + int(round(math.sin(f * 3.2) * 1.2 + sway * f * f))
        if k % 2 == 0:
            _stamp(arr, _LEAF, x + 1, y - 2)
        else:
            _stamp(arr, _LEAF, x - 7, y - 2, flip=True)
    tx = cx + int(round(math.sin(3.2) * 1.2 + sway))
    if stage == 3:
        _stamp(arr, _BUD, tx - 1, top - 6)
    elif stage == 4:
        fy = top - 6
        if glow > 0:
            g = np.zeros_like(arr)
            for y in range(H):
                for x in range(W):
                    r = math.hypot(x - tx, y - fy)
                    if 6.8 < r <= 9.6:
                        a = int((80 if r <= 8.2 else 34) * glow)
                        g[y, x] = (236, 248, 255, a)
            under = arr[..., 3] == 0
            arr[under] = g[under]
        _bloom(arr, tx, fy)
    return Image.fromarray(arr)


def moonflower_icon(size=32) -> Image.Image:
    """視窗圖示：正面的月光花（點陣），以最近鄰放大到 size。"""
    arr = np.zeros((16, 16, 4), np.uint8)
    _bloom(arr, 7.5, 7.5)
    return Image.fromarray(arr).resize((size, size), Image.NEAREST)


def flower_stage(age_s: float) -> int:
    st = 0
    for i, (t, _) in enumerate(FLOWER_STAGES):
        if age_s >= t:
            st = i
    return st


def is_night() -> bool:
    h = time.localtime().tm_hour
    return h >= 18 or h < 6


# ------------------------------------------------------------------ 道具／粒子（點陣）
def _pix(rows, cols):
    h, w = len(rows), max(len(r) for r in rows)
    a = np.zeros((h, w, 4), np.uint8)
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            if ch != ".":
                a[y, x] = cols[ch]
    return Image.fromarray(a)


_PC = {
    "o": OUTLINE,
    "p": (250, 190, 206, 255),  # 粉色糰子
    "P": (255, 222, 230, 255),
    "w": (246, 244, 238, 255),  # 白色糰子
    "W": (255, 255, 255, 255),
    "g": (166, 210, 144, 255),  # 綠色糰子
    "G": (198, 232, 176, 255),
    "k": (150, 112, 78, 255),  # 竹籤
    "c": (232, 230, 244, 255),  # 枕頭
    "C": (200, 196, 222, 255),
    "f": (250, 252, 255, 255),  # 泡沫
    "F": (214, 228, 246, 255),
    "b": (176, 214, 244, 255),  # 泡泡框
    "i": (214, 236, 255, 110),  # 泡泡內
    "z": (226, 226, 255, 255),
    "h": (255, 150, 182, 255),
    "s": (255, 248, 206, 255),
    "d": (150, 200, 255, 255),
    "u": (178, 172, 168, 255),
    "r": (206, 164, 116, 255),
}


def draw_dango(bites=0) -> Image.Image:
    """三色糰子：粉／白／綠，每咬一口少一顆（由上往下）。"""
    balls = [("p", "P"), ("w", "W"), ("g", "G")]
    rows = []
    for i, (c, hl) in enumerate(balls):
        if i < bites:
            rows += [".......", "...k...", "...k...", "...k..."] if i == 0 else ["...k...", "...k...", "...k...", "...k..."]
            continue
        rows += [
            "..ooo..",
            f".o{hl}{c}{c}o.",
            f"o{c}{c}{c}{c}{c}o",
            f".o{c}{c}{c}o.",
        ]
    rows += ["...k...", "...k...", "...k..."]
    return _pix(rows, _PC)


PILLOW = _pix([
    "..oooooooooooooooooo..",
    ".occccccccccccccccccco.",
    "occccccccccccccccccccco",
    "oCcccccccccccccccccCCCo",
    ".oCCCCCCCCCCCCCCCCCCCo.",
    "..ooooooooooooooooooo..",
], _PC)

FOAM = _pix([
    "....ff...ff.....",
    "..ffffff.fffff..",
    ".ffffffffffffff.",
    "fffFfffffffFffff",
    ".FFffffFFfffFFf.",
    "..FF.FFF..FFF...",
], _PC)

PARTICLES = {
    "bubble": _pix([".bbb.", "bWiib", "biiib", "biiib", ".bbb."], dict(_PC, W=(255, 255, 255, 230))),
    "z": _pix(["zzzz", "..z.", ".z..", "zzzz"], _PC),
    "crumb": _pix(["r"], _PC),
    "drop": _pix(["d", "d"], _PC),
    "spark": _pix([".s.", "sss", ".s."], _PC),
    "dust": _pix(["uu", "uu"], _PC),
    "heart": _pix([".h.h.", "hhhhh", ".hhh.", "..h.."], _PC),
}

# ------------------------------------------------------------------ 台詞
LINES = {
    "idle": ["……", "今天也做了好夢嗎？", "我在聽風的聲音。", "要不要一起發呆？", "夢裡下了雪。", "…嗯。",
             "你在忙嗎？", "我會乖乖待著。", "月光花快開了。", "山谷裡很安靜。"],
    "night": ["月光花在發光。", "晚上了，要早點睡喔。", "星星很多。", "夜晚是我的時間。"],
    "click": ["…有事嗎？", "被戳到了。", "嗯？", "摸摸頭…可以。", "不要一直戳。", "我在。"],
    "eat": ["好吃。", "…還想要。", "甜甜的。", "謝謝招待。"],
    "hungry": ["肚子餓了…", "想吃糰子。", "…咕嚕。"],
    "dirty": ["想洗澡…", "有點髒了。"],
    "sleepy": ["好睏…", "眼睛睜不開了。"],
    "trip": ["好痛…", "嗚…", "……跌倒了。", "地板偷襲我。"],
    "chat": ["……嗯，我有在聽。", "這樣啊。", "你說的話，我會記在夢裡。", "我不太懂，但是沒關係。",
             "要不要一起種花？", "嗯嗯。", "…你今天辛苦了。"],
}

CHAT_RULES = [
    (("吃", "餓", "糰子", "點心", "飯"), "eat", "好，開動了。"),
    (("洗", "澡", "髒"), "bath", "那我去洗澡。"),
    (("醒", "起床"), "wake", "…醒了。"),
    (("睡", "累", "晚安", "休息"), "sleep", "那我睡一下。"),
    (("爬", "窗"), "climb", "爬上去看看。"),
    (("下來",), "jump_down", "好。"),
    (("跳",), "bounce", "跳跳。"),
    (("翻",), "frontflip", "看好囉。"),
    (("轉",), "spin", "轉一圈。"),
    (("花", "種"), "plant", "來種月光花。"),
    (("吊",), "hang", "倒過來看世界。"),
    (("走", "散步"), "walk", "去散步。"),
    (("跌", "摔"), "trip", "…才不會跌倒。"),
    (("早安", "你好", "嗨", "哈囉", "hi", "hello"), None, "…你好。"),
    (("喜歡", "愛"), None, "……我也是。"),
    (("名字", "你是誰"), None, "我是做夢的神明。"),
    (("謝謝",), None, "不客氣。"),
    (("山谷", "家"), None, "我住在永遠是夜晚的山谷。"),
]


def respond(text: str):
    t = text.lower()
    for keys, act, reply in CHAT_RULES:
        if any(k in t for k in keys):
            return reply, act
    return random.choice(LINES["chat"]), None


# ------------------------------------------------------------------ 照顧數值
CARE_KEYS = ("hunger", "clean", "mood", "energy")
CARE_NAMES = {"hunger": "飽食", "clean": "清潔", "mood": "心情", "energy": "體力"}
CARE_DECAY = {"hunger": 10.0, "clean": 6.0, "mood": 5.0, "energy": 8.0}  # 每小時下降
SLEEP_ENERGY_PER_S = 2.5


class Care:
    def __init__(self, path: Path | None):
        self.path = path
        self.v = {k: 80.0 for k in CARE_KEYS}
        self.save_t = 0.0
        try:
            d = json.loads(path.read_text(encoding="utf-8"))
            self.v.update({k: float(d["v"][k]) for k in CARE_KEYS})
            self.decay(min(max(time.time() - float(d["t"]), 0), 48 * 3600), False)
        except Exception:
            pass

    def decay(self, sec, sleeping):
        h = sec / 3600
        for k in CARE_KEYS:
            if k == "energy" and sleeping:
                continue
            self.v[k] -= CARE_DECAY[k] * h
        low = sum(1 for k in ("hunger", "clean", "energy") if self.v[k] < 25)
        self.v["mood"] -= low * 3 * h
        if sleeping:
            self.v["energy"] += SLEEP_ENERGY_PER_S * sec
        for k in CARE_KEYS:
            self.v[k] = max(0.0, min(100.0, self.v[k]))

    def tick(self, dt, sleeping):
        self.decay(dt, sleeping)
        self.save_t += dt
        if self.save_t > 30:
            self.save()

    def add(self, k, n):
        self.v[k] = max(0.0, min(100.0, self.v[k] + n))

    def save(self):
        self.save_t = 0.0
        if not self.path:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps({"v": self.v, "t": time.time()}), encoding="utf-8")
        except Exception:
            pass


# ------------------------------------------------------------------ 說話泡泡（Cubic 11 點陣字）
FONT_PATH = ROOT / "fonts" / "Cubic_11.ttf"
_font_cache = {}


def pixel_font(size=11):
    if size not in _font_cache:
        try:
            from PIL import ImageFont

            _font_cache[size] = ImageFont.truetype(str(FONT_PATH), size)
        except Exception:
            from PIL import ImageFont

            _font_cache[size] = ImageFont.load_default()
    return _font_cache[size]


def _wrap(text, n=10):
    out, line = [], ""
    for ch in text:
        line += ch
        if len(line) >= n:
            out.append(line)
            line = ""
    if line:
        out.append(line)
    return out or [""]


def render_bubble(text: str) -> Image.Image:
    """原生解析度的說話泡泡（白底、深色外框、下方小尾巴）。"""
    font = pixel_font(11)
    lines = _wrap(text, 10)
    tmp = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    tw = max(int(tmp.textlength(ln, font=font)) for ln in lines)
    lh = 12
    w, h = tw + 8, lh * len(lines) + 5
    img = Image.new("RGBA", (w, h + 4), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.fontmode = "1"
    d.rectangle((1, 0, w - 2, h - 1), fill=(250, 250, 252, 255))
    d.rectangle((0, 1, w - 1, h - 2), fill=(250, 250, 252, 255))
    o = OUTLINE
    d.line((2, 0, w - 3, 0), fill=o)
    d.line((2, h - 1, w - 3, h - 1), fill=o)
    d.line((0, 2, 0, h - 3), fill=o)
    d.line((w - 1, 2, w - 1, h - 3), fill=o)
    for x, y in ((1, 1), (w - 2, 1), (1, h - 2), (w - 2, h - 2)):
        img.putpixel((x, y), o)
    cx = w // 2
    for i, (a, b) in enumerate(((-2, 2), (-1, 1), (0, 0))):
        y = h - 1 + i
        d.line((cx + a, y, cx + b, y), fill=(250, 250, 252, 255))
        img.putpixel((cx + a - 1, y), o)
        img.putpixel((cx + b + 1, y), o)
    img.putpixel((cx, h + 2), o)
    for i, ln in enumerate(lines):
        d.text((4, 2 + i * lh), ln, font=font, fill=(52, 46, 64, 255))
    return img


# ------------------------------------------------------------------ 背景：永夜的月光花黑色山谷
_BAYER = np.array([[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]]) / 16.0


def _dither_gradient(h, w, c0, c1, steps=6):
    t = np.linspace(0, 1, h)[:, None] * np.ones((1, w))
    q = np.floor(t * steps + _BAYER[np.arange(h)[:, None] % 4, np.arange(w)[None, :] % 4]) / steps
    q = np.clip(q, 0, 1)[..., None]
    return (np.array(c0) * (1 - q) + np.array(c1) * q).astype(np.uint8)


def draw_valley(t: float, w=200, h=125) -> Image.Image:
    """黑色山谷：永遠的黑夜、滿谷月光花、飄著螢光花粉。"""
    sky = _dither_gradient(h, w, (4, 4, 12), (20, 16, 38), 7)
    img = np.zeros((h, w, 4), np.uint8)
    img[..., :3] = sky
    img[..., 3] = 255
    rng = np.random.default_rng(7)
    # 星星
    for i in range(70):
        x, y = rng.integers(0, w), rng.integers(0, int(h * 0.55))
        tw = 0.5 + 0.5 * math.sin(t * rng.uniform(1, 3) + i)
        if tw > 0.35:
            v = int(150 + 100 * tw)
            img[y, x, :3] = (v, v, min(255, v + 20))
    # 月亮（滿月＋光暈）
    mx, my, mr = int(w * 0.72), int(h * 0.2), 9
    yy, xx = np.mgrid[0:h, 0:w]
    rr = np.hypot(xx - mx, yy - my)
    halo = (rr < mr + 7) & (rr >= mr)
    dith = _BAYER[yy % 4, xx % 4]
    img[halo & (dith < 0.5 - (rr - mr) / 16), :3] = (40, 42, 70)
    moon = rr < mr
    img[moon, :3] = (226, 228, 214)
    img[moon & (np.hypot(xx - mx - 3, yy - my + 2) < 2.5), :3] = (204, 206, 194)
    img[moon & (np.hypot(xx - mx + 3, yy - my - 3) < 1.8), :3] = (208, 210, 198)
    # 遠山（深紫灰）與近山（純黑）：中間低的 V 形山谷
    xs = np.arange(w)
    far = h * 0.52 + 10 * np.cos(xs / w * math.pi * 2) + 3 * np.sin(xs * 0.31) + 2 * np.sin(xs * 0.83)
    near_l = h * 0.38 + xs * 0.55 + 2 * np.sin(xs * 0.5)
    near_r = h * 0.38 + (w - xs) * 0.55 + 2 * np.sin(xs * 0.45 + 1)
    near = np.minimum(near_l, near_r)
    for x in range(w):
        img[int(far[x]):, x, :3] = (22, 19, 34)
        img[int(far[x]), x, :3] = (40, 36, 60)  # 遠山稜線
        ny = max(int(near[x]), 0)
        img[ny:, x, :3] = (8, 8, 12)
        if ny < h:
            img[ny, x, :3] = (52, 50, 78)  # 近山被月光照亮的稜線
            if ny + 1 < h and x % 3:
                img[ny + 1, x, :3] = (26, 26, 40)
    # 山谷底（黑色草地）
    floor_y = int(h * 0.74)
    img[floor_y:, :, :3] = (6, 6, 10)
    for x in range(0, w, 2):
        gh = rng.integers(1, 3)
        img[floor_y - gh:floor_y, x, :3] = (12, 14, 18)
    # 薄霧
    mist = (yy > floor_y - 6) & (yy < floor_y + 2) & (dith < 0.18 + 0.08 * math.sin(t * 0.7))
    img[mist, :3] = np.minimum(img[mist, :3].astype(int) + 22, 255).astype(np.uint8)
    # 月光花：遠處小點、山坡上小花、近處大花
    def flower_dot(x, y, size, glow):
        g = int(150 + 105 * glow)
        if size == 1:
            if 0 <= y < h and 0 <= x < w:
                img[y, x, :3] = (g, g, min(255, g + 10))
        else:
            for dx, dy in ((0, 0), (1, 0), (-1, 0), (0, 1), (0, -1)):
                X, Y = x + dx, y + dy
                if 0 <= X < w and 0 <= Y < h:
                    img[Y, X, :3] = (238, 240, 232) if (dx, dy) != (0, 0) else (214, 226, 150)

    frng = np.random.default_rng(11)
    for i in range(160):  # 山坡與谷底的小花
        x = int(frng.integers(0, w))
        top = int(min(near[x], h - 1)) + 2
        if top >= h - 1:
            continue
        y = int(frng.integers(top, h))
        size = 1 if y < floor_y else 3
        flower_dot(x, y, size, 0.5 + 0.5 * math.sin(t * 1.5 + i))
    # 螢光花粉
    for i in range(18):
        px = (frng.uniform(0, w) + t * frng.uniform(1, 4)) % w
        py = floor_y - 4 - ((t * frng.uniform(2, 5) + i * 7) % 30)
        if 0 <= int(py) < h and (int(t * 3 + i) % 4):
            img[int(py), int(px), :3] = (230, 255, 220)
    out = Image.fromarray(img)
    # 近景大朵月光花（會發光）
    for i, fx in enumerate((12, 40, w - 40, w - 12)):
        fl = draw_moonflower(4, int(round(math.sin(t * 1.2 + i) * 1.2)), 0.75 + 0.25 * math.sin(t * 2 + i))
        out.alpha_composite(fl, (fx - FLOWER_W // 2, h - FLOWER_H + 6))
    return out


class Rig:
    """8 張 64×64 點陣視圖 + 類 Live2D 參數變形（以整數像素位移，維持點陣風格）。

    物理與參數以「螢幕像素」計算；繪製在原生點陣解析度進行，最後以最近鄰整數倍放大。
    """

    def __init__(self, scale: int, sprites: dict[str, Image.Image]):
        self.s = s = int(scale)
        self.U = SRC * KN * s  # 一個「角色高度」單位（螢幕像素）
        self.C = (CANVAS / 2, PAD + (CENTER_Y - SRC_Y0) * KN)  # 原生畫布上的旋轉中心
        self.df = (FEET_Y - CENTER_Y) * KN * s
        self.dh = (CENTER_Y - HEAD_Y) * KN * s
        self.hw = 0.2 * self.U
        self.W = WIN_N * s
        self.views: dict[tuple[str, bool], np.ndarray] = {}
        for key, sp in sprites.items():
            canvas = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
            canvas.paste(sp, (PAD, PAD))
            self.views[(key, False)] = np.asarray(canvas).copy()
            self.views[(key, True)] = np.asarray(ImageOps.mirror(canvas)).copy()
        yy, xx = np.mgrid[0:CANVAS, 0:CANVAS].astype(np.float64)
        self.yy, self.xx = yy.astype(np.int32), xx.astype(np.int32)
        src_y = (yy + 0.5 - PAD) / KN + SRC_Y0
        v = src_y / SRC
        u = (xx + 0.5 - CANVAS / 2) / KN / CROP_HALF
        au = np.abs(u)
        self.u = u
        self.w_lean = np.clip((0.93 - v) / 0.9, 0, 1)
        self.w_head = smoothstep(0.56, 0.36, v)
        self.w_hair = smoothstep(0.12, 0.45, au) * smoothstep(0.28, 0.5, v) * smoothstep(0.84, 0.7, v)
        self.w_skirt = smoothstep(0.58, 0.78, v) * smoothstep(0.9, 0.8, v)
        self.w_legs = smoothstep(0.8, 0.93, v)
        self.w_breath = smoothstep(0.8, 0.42, v)
        self.w_wing = smoothstep(0.14, 0.03, v) * smoothstep(0.1, 0.3, au)
        # 手臂（側面走路用）：袖子＋白色袖口＋小手，以肩膀為軸擺動
        dress = (70, 66, 76, 255)
        arm_cols = {"o": OUTLINE, "#": dress, "W": (236, 232, 236, 255), "s": (250, 234, 232, 255)}
        self.arm_front = self._pattern(ARM_PATTERN, arm_cols)
        dark = {k: (int(c[0] * 0.7), int(c[1] * 0.7), int(c[2] * 0.7), 255) if k != "o" else c
                for k, c in arm_cols.items()}
        self.arm_back = self._pattern(ARM_PATTERN, dark)
        # 側面視圖：把腿切出來，走路時複製成前後兩隻腳交替擺動
        self.legs = {}
        for key in ("left", "right"):
            for mir in (False, True):
                arr = self.views[(key, mir)]
                opaque = arr[..., 3] > 0
                rows = np.nonzero(opaque.any(1))[0]
                bot = int(rows.max())
                top = bot
                while top - 1 >= 0 and 0 < opaque[top - 1].sum() <= 10:
                    top -= 1
                leg = arr.copy()
                leg[:top] = 0
                base = arr.copy()
                base[top:] = 0
                back = leg.copy()
                inner = (back[..., 3] > 0) & ~np.all(back[..., :3] == OUTLINE[:3], axis=-1)
                back[inner, :3] = (back[inner, :3] * 0.72).astype(np.uint8)
                facing = 1 if (key == "right") != mir else -1
                # 肩膀位置：脖子下方幾列深色衣服的中央
                lum = arr[..., :3].astype(np.float32) @ np.array([0.299, 0.587, 0.114], np.float32)
                dark_px = (arr[..., 3] > 0) & (lum < 90)
                sy0 = PAD + SHOULDER_ROW
                xs = np.nonzero(dark_px[sy0:sy0 + 4].any(0))[0]
                sx0 = int(np.median(xs)) if xs.size else CANVAS // 2
                self.legs[(key, mir)] = (base, leg, back, top, bot, facing, (sx0, sy0))
        # 正面轉頭：頭部換成斜側視圖
        self.head_cut = PAD + NECK_ROW

    @staticmethod
    def _pattern(rows, cols):
        h, w = len(rows), len(rows[0])
        a = np.zeros((h, w, 4), np.uint8)
        for y, row in enumerate(rows):
            for x, ch in enumerate(row):
                if ch != ".":
                    a[y, x] = cols[ch]
        return a

    @staticmethod
    def _stamp_rotated(out, spr, pivot, angle):
        """把小圖以頂端中央為軸旋轉（最近鄰）後貼到 out 的 pivot 位置。"""
        h, w = spr.shape[:2]
        px, py = (w - 1) / 2, 0.5
        r = math.radians(angle)
        c, s = math.cos(r), math.sin(r)
        R = int(math.ceil(math.hypot(w, h))) + 1
        for oy in range(-2, R):
            for ox in range(-R, R + 1):
                # 反向旋轉找來源像素
                sxf = ox * c + oy * s + px
                syf = -ox * s + oy * c + py
                ix, iy = int(math.floor(sxf + 0.5)), int(math.floor(syf))
                if 0 <= ix < w and 0 <= iy < h and spr[iy, ix, 3]:
                    X, Y = pivot[0] + ox, pivot[1] + oy
                    if 0 <= X < out.shape[1] and 0 <= Y < out.shape[0]:
                        out[Y, X] = spr[iy, ix]

    def compose_walk(self, view, phase: float, stride: float) -> np.ndarray:
        """前後腳交替：以髖部為軸做像素剪切，往前擺的那隻腳抬起 1~2 格。
        手臂與同側腳反向擺動（前手配前腳反向、後手配後腳反向），避免同手同腳。"""
        base, leg, back, top, bot, facing, shoulder = self.legs[view]
        out = np.zeros_like(base)
        h = max(bot - top, 1)
        swing_arm = ARM_SWING * math.sin(phase) * facing
        # 後手（畫在身體後面）：跟後腳反向 → 與前腳同向
        self._stamp_rotated(out, self.arm_back, (shoulder[0] + facing, shoulder[1]), -swing_arm)
        for img, sgn in ((back, -1), (leg, 1)):
            swing = sgn * stride * math.sin(phase) * facing
            lift = int(round(max(0.0, sgn * math.cos(phase)) * 1.6))
            for y in range(top, bot + 1):
                row = img[y]
                xs = np.nonzero(row[:, 3])[0]
                if xs.size == 0:
                    continue
                dy = y - lift
                if not 0 <= dy < CANVAS:
                    continue
                dx = xs + int(round(swing * (y - top) / h))
                ok = (dx >= 0) & (dx < CANVAS)
                out[dy, dx[ok]] = row[xs[ok]]
        m = base[..., 3] > 0
        out[m] = base[m]
        # 前手（畫在身體前面）：跟前腳反向
        self._stamp_rotated(out, self.arm_front, shoulder, swing_arm)
        return out

    def compose_head(self, body: np.ndarray, head_view) -> np.ndarray:
        out = body.copy()
        out[: self.head_cut] = 0
        head = self.views[head_view]
        hm = head[: self.head_cut, :, 3] > 0
        out[: self.head_cut][hm] = head[: self.head_cut][hm]
        return out

    def deform(self, arr: np.ndarray, p: dict) -> Image.Image:
        s = self.s
        dx = (
            p["lean"] * self.w_lean
            + p["head"] * self.w_head
            + p["hair"] * self.w_hair
            + p["skirt"] * self.w_skirt
            + p["flare"] * self.u * (CROP_HALF * KN * s) * self.w_skirt
            + p["legs"] * self.w_legs
            + p.get("look_x", 0.0) * self.w_head
        ) / s
        dy = (-p["breath"] * self.w_breath + p["wing"] * self.w_wing + p.get("look_y", 0.0) * self.w_head) / s
        sx = self.xx - np.rint(dx).astype(np.int32)
        sy = self.yy - np.rint(dy).astype(np.int32)
        ok = (sx >= 0) & (sx < CANVAS) & (sy >= 0) & (sy < CANVAS)
        out = arr[np.clip(sy, 0, CANVAS - 1), np.clip(sx, 0, CANVAS - 1)]
        out[~ok] = 0
        return Image.fromarray(out)

    def render(self, view, params, rot, sx, sy, frac=(0.0, 0.0)) -> Image.Image:
        arr = self.views[view]
        if params.get("stride", 0) > 0 and view in self.legs:
            arr = self.compose_walk(view, params["gait"], params["stride"])
        elif params.get("head_view") and view == ("front", False):
            arr = self.compose_head(arr, params["head_view"])
        img = self.deform(arr, params)
        W = WIN_N
        r = math.radians(rot)
        c, s = math.cos(r), math.sin(r)
        if abs(c) < 1e-9:
            c = 0.0
        if abs(s) < 1e-9:
            s = 0.0
        sx = max(sx, 0.05)
        sy = max(sy, 0.05)
        wcx, wcy = W / 2, W / 2
        a, b = c / sx, s / sx
        d, e = -s / sy, c / sy
        Cx, Cy = self.C
        coeffs = (a, b, Cx - a * wcx - b * wcy, d, e, Cy - d * wcx - e * wcy)
        # 回傳原生解析度（WIN_N×WIN_N）；放大在送進視窗時以整數倍複製像素完成
        return img.transform((W, W), Image.AFFINE, coeffs, Image.NEAREST)

# ------------------------------------------------------------------ pet logic
class Spring:
    def __init__(self, k, d):
        self.k, self.d, self.x, self.v = k, d, 0.0, 0.0

    def step(self, target, dt):
        self.v += (self.k * (target - self.x) - self.d * self.v) * dt
        self.x += self.v * dt
        return self.x


class Pet:
    ANIM_KEYS = ("lean", "head", "legs", "wing", "flare")

    def __init__(self, rig: Rig, work_fn):
        self.work_fn = work_fn
        self.set_rig(rig)
        l, t, r, b = work_fn((0, 0))
        self.P = [(l + r) / 2, t + (b - t) * 0.35]
        self.lastP = list(self.P)
        self.rot = 0.0
        self.sx = self.sy = 1.0
        self.squeeze_x = self.squeeze_y = 1.0
        self.yaw = 0.0
        self.view = ("front", False)
        self.view_rot = 0.0
        self.a = {k: 0.0 for k in self.ANIM_KEYS}
        self.a_s = dict(self.a)
        self.gait = 0.0  # 走路相位
        self.stride = 0.0  # 跨步幅度（點陣像素），0 = 不走路
        self.jelly = Spring(260, 9)
        self.hair = Spring(70, 5.5)
        self.skirt = Spring(95, 7)
        self.flare = Spring(55, 5)
        self.t = 0.0
        self.dt = 1 / 30
        self.work = work_fn(self.P)
        self.action = None
        self.queue: list = []
        self.auto = True
        self.last_kind = "idle"
        self.dragging = False
        self.mouse = (0.0, 0.0)
        self.v_world = (0.0, 0.0)
        self.on_plant = None  # callback(x, floor_y)：種月光花
        self.care = None  # Care
        self.props: dict = {}  # name -> (img, x, bottom_y, layer)
        self.particles: list = []
        self.speech = None  # (text, until_t)
        self.sleeping = False
        self.wake_req = False
        self.platform = None  # 站在某個視窗頂端：{"hwnd", "rect"}
        self.win_rect_fn = None
        self.windows_fn = None
        self.cursor_pos = None
        self.look_enabled = True
        self.look = [0.0, 0.0]
        self.head_view = None
        self.base_work = self.work
        self.run(self.act_fall(0, 0, 0))

    def set_rig(self, rig: Rig):
        self.rig = rig
        self.U = rig.U
        self.G = 9.0 * rig.U

    # ---------------------------------------------------------- geometry
    def total_scale(self):
        j = self.jelly.x
        return self.sx * self.squeeze_x * (1 + 0.7 * j), self.sy * self.squeeze_y * (1 - j)

    def extent(self):
        sxT, syT = self.total_scale()
        df, dh, hw = self.rig.df, self.rig.dh, self.rig.hw
        pts = [(0, df), (0, -dh), (hw, 0), (-hw, 0), (hw * 0.7, df * 0.8), (-hw * 0.7, df * 0.8),
               (hw * 0.8, -dh * 0.6), (-hw * 0.8, -dh * 0.6)]
        ys = [rot2(x * sxT, y * syT, self.rot)[1] for x, y in pts]
        return min(ys), max(ys)

    def feet_vec(self):
        sxT, syT = self.total_scale()
        return rot2(0, self.rig.df * syT, self.rot)

    def place_feet(self, fx, fy):
        vx, vy = self.feet_vec()
        self.P[0], self.P[1] = fx - vx, fy - vy

    def ground(self, lift=0.0):
        l, t, r, b = self.work
        hw = self.rig.hw
        self.P[0] = min(max(self.P[0], l + hw), r - hw)
        self.P[1] = b - lift - self.extent()[1]

    def grounded(self):
        return self.P[1] + self.extent()[1] >= self.work[3] - 3

    def set_yaw(self, y):
        self.yaw = y % 360.0
        self.view = YAW_VIEWS[int(round(self.yaw / 45.0)) % 8]
        self.view_rot = 0.0
        self.squeeze_x = 0.72 + 0.28 * abs(math.cos(math.radians(4 * self.yaw)))

    def kick(self, impact_vy, scale=1.0):
        self.jelly.v += min(abs(impact_vy) / self.U * 0.75, 3.6) * scale

    # ---------------------------------------------------------- frame update
    def step(self, dt):
        self.dt = dt
        self.t += dt
        self.update_platform()
        vx = (self.P[0] - self.lastP[0]) / dt
        vy = (self.P[1] - self.lastP[1]) / dt
        self.lastP = list(self.P)
        self.v_world = (vx, vy)
        bvx, bvy = rot2(vx, vy, -self.rot)
        U = self.U
        lim = 0.07 * U
        self.hair.step(max(-lim, min(lim, -bvx * 0.045)), dt)
        self.skirt.step(max(-lim, min(lim, -bvx * 0.035)), dt)
        self.flare.step(max(-0.05, min(0.2, bvy / U * 0.06)), dt)
        self.jelly.step(0.0, dt)
        self.jelly.x = max(-0.3, min(0.35, self.jelly.x))

        if self.dragging:
            self.drag_step()
        else:
            if self.action is None:
                self.action = self.next_action()
            try:
                next(self.action)
            except StopIteration:
                self.action = None
        f = min(1.0, dt * 14)
        for k in self.ANIM_KEYS:
            self.a_s[k] += (self.a[k] - self.a_s[k]) * f
        self.update_look(dt)
        self.update_particles(dt)
        if self.care:
            self.care.tick(dt, self.sleeping)

    def params(self):
        U, t, a = self.U, self.t, self.a_s
        gx, gy = math.sin(math.radians(self.rot)), math.cos(math.radians(self.rot))
        return {
            "lean": a["lean"],
            "head": a["head"] + self.hair.x * 0.25,
            "breath": (0.016 * U * math.sin(t * 2 * math.pi / 4.6)) if self.sleeping
            else 0.008 * U * math.sin(t * 2 * math.pi / 3.4),
            "hair": self.hair.x + gx * 0.04 * U,
            "skirt": self.skirt.x + gx * 0.03 * U,
            "flare": self.flare.x + a["flare"] + (1 - gy) * 0.03,
            "legs": a["legs"] + self.skirt.x * 0.4,
            "wing": a["wing"] + 0.004 * U * math.sin(t * 2.1),
            "gait": self.gait,
            "stride": self.stride,
            "look_x": self.look[0],
            "look_y": self.look[1],
            "head_view": self.head_view,
        }

    def facing(self):
        return 1 if self.view in (("right", False), ("left", True)) else -1

    def frame(self):
        W = self.rig.W
        ox, oy = self.P[0] - W / 2, self.P[1] - W / 2
        wx, wy = math.floor(ox), math.floor(oy)
        sxT, syT = self.total_scale()
        img = self.rig.render(self.view, self.params(), self.rot + self.view_rot, sxT, syT, (ox - wx, oy - wy))
        if self.props or self.particles:
            img = self.compose_extras(img)
        return img, wx, wy

    def compose_extras(self, img):
        s = self.rig.s
        half = WIN_N / 2

        def at(spr, x, y, anchor="bottom"):
            nx = (x - self.P[0]) / s + half - spr.width / 2
            ny = (y - self.P[1]) / s + half - (spr.height if anchor == "bottom" else spr.height / 2)
            return int(round(nx)), int(round(ny))

        back = [v for v in self.props.values() if v[3] == "back"]
        front = [v for v in self.props.values() if v[3] != "back"]
        if back:
            base = Image.new("RGBA", img.size, (0, 0, 0, 0))
            for spr, x, by, _ in back:
                base.paste(spr, at(spr, x, by), spr)
            base.alpha_composite(img)
            img = base
        else:
            img = img.copy()
        for spr, x, by, _ in front:
            img.paste(spr, at(spr, x, by), spr)
        for q in self.particles:
            if q["age"] > q["life"] * 0.7 and int(q["age"] * 14) % 2:
                continue
            spr = PARTICLES[q["kind"]]
            img.paste(spr, at(spr, q["x"], q["y"], "center"), spr)
        return img

    # ---------------------------------------------------------- action plumbing
    def over(self, dur):
        t = 0.0
        while t < dur:
            yield t / dur
            t += self.dt
        yield 1.0

    def reset_pose(self):
        for k in self.ANIM_KEYS:
            self.a[k] = 0.0
        self.sx = self.sy = 1.0
        self.squeeze_y = 1.0
        self.view_rot = 0.0
        self.stride = 0.0
        self.squeeze_x = 1.0
        self.props.clear()
        self.sleeping = False
        self.set_yaw(round(self.yaw / 45.0) * 45.0)

    def _chain(self, gen):
        if not self.grounded() or abs(wrap180(self.rot)) > 5:
            self.set_yaw(self.yaw)
            yield from self.act_fall(0, 0, 0, keep_rot=True)
        self.reset_pose()
        yield from gen

    def run(self, gen):
        self.dragging = False
        self.queue.clear()
        self.action = self._chain(gen)

    def next_action(self):
        if self.queue:
            return self._chain(self.queue.pop(0)())
        if not self.auto:
            return self._chain(self.act_idle(2.0, face=False))
        c = self.care
        if c and c.v["energy"] < 15 and not self.platform:
            self.last_kind = "sleep"
            return self._chain(self.act_sleep())
        if self.last_kind != "idle":
            self.last_kind = "idle"
            if c and c.v["hunger"] < 20 and random.random() < 0.35:
                self.say(random.choice(LINES["hungry"]))
            elif c and c.v["clean"] < 20 and random.random() < 0.3:
                self.say(random.choice(LINES["dirty"]))
            elif c and c.v["energy"] < 25 and random.random() < 0.3:
                self.say(random.choice(LINES["sleepy"]))
            elif random.random() < 0.22:
                pool = LINES["night"] if (is_night() and random.random() < 0.5) else LINES["idle"]
                self.say(random.choice(pool))
            return self._chain(self.act_idle(random.uniform(1.5, 4.0)))
        if self.platform:
            choices = [
                ("walk", 4.0, lambda: self.act_walk()),
                ("look", 1.2, lambda: self.act_look()),
                ("spin", 0.8, lambda: self.act_spin()),
                ("bounce", 0.6, lambda: self.act_bounce((0.45, 0.2))),
                ("jump_down", 1.4, lambda: self.act_jump_down()),
            ]
        else:
            choices = [
                ("walk", 4.0, lambda: self.act_walk()),
                ("look", 1.2, lambda: self.act_look()),
                ("spin", 1.0, lambda: self.act_spin()),
                ("bounce", 1.2, lambda: self.act_bounce()),
                ("frontflip", 0.7, lambda: self.act_frontflip()),
                ("somersault", 0.7, lambda: self.act_somersault()),
                ("hang", 0.8, lambda: self.act_hang()),
            ]
            if self.windows_fn:
                choices.append(("climb", 0.9, lambda: self.act_climb()))
        r = random.uniform(0, sum(w for _, w, _ in choices))
        for kind, w, fn in choices:
            r -= w
            if r <= 0:
                break
        self.last_kind = kind
        return self._chain(fn())

    # ---------------------------------------------------------- building blocks
    def turn_to(self, target, per45=0.1):
        cur = self.yaw
        diff = wrap180(target - cur)
        if abs(diff) < 1:
            return
        for p in self.over(per45 * abs(diff) / 45):
            self.set_yaw(cur + diff * ease(p))
            self.ground()
            yield
        self.set_yaw(target)

    def settle(self, dur=0.35):
        r0 = wrap180(self.rot)
        sx0, sy0 = self.sx, self.sy
        for p in self.over(dur):
            e = ease(p)
            self.rot = r0 * (1 - e)
            self.sx = sx0 + (1 - sx0) * e
            self.sy = sy0 + (1 - sy0) * e
            self.ground()
            yield
        self.rot = 0.0

    def crouch(self, dur=0.16, depth=0.18):
        for p in self.over(dur):
            e = ease(p)
            self.sy = 1 - depth * e
            self.sx = 1 + depth * 0.7 * e
            self.ground()
            yield
        self.sx = self.sy = 1.0
        self.jelly.x = -depth * 0.8  # 起跳拉長

    def airborne(self, vx, vy, spin=0.0, cb=None):
        T = 0.0
        hw = self.rig.hw
        while True:
            dt = self.dt
            vy += self.G * dt
            self.P[0] += vx * dt
            self.P[1] += vy * dt
            self.rot += spin * dt
            l, t, r, b = self.work
            if self.P[0] < l + hw:
                self.P[0], vx = l + hw, abs(vx) * 0.6
            elif self.P[0] > r - hw:
                self.P[0], vx = r - hw, -abs(vx) * 0.6
            if cb:
                cb(T)
            T += dt
            lo, hi = self.extent()
            if self.P[1] + lo < t and vy < 0:
                self.P[1], vy = t - lo, abs(vy) * 0.4
            if vy > 0 and self.P[1] + hi >= b:
                self.P[1] = b - hi
                return vy, vx
            yield

    # ---------------------------------------------------------- actions
    def act_idle(self, dur, face=True):
        if face:
            yield from self.turn_to(0)
        for _ in self.over(dur):
            t = self.t
            self.a["head"] = 0.012 * self.U * math.sin(t * 1.3)
            self.a["lean"] = 0.006 * self.U * math.sin(t * 0.9)
            self.ground()
            yield

    def act_look(self):
        yield from self.turn_to(0)
        for target in (315, 0, 45, 0):
            yield from self.turn_to(target, 0.14)
            yield from self.act_idle(random.uniform(0.5, 1.0), face=False)

    def act_walk(self, direction=0, dist=None, face_front=True, events=True):
        U = self.U
        l, t, r, b = self.work
        if direction == 0:
            room_r, room_l = r - self.P[0], self.P[0] - l
            direction = 1 if random.random() < room_r / max(room_r + room_l, 1) else -1
        dist = dist or random.uniform(1.5, 5.0) * U
        yield from self.turn_to(90 if direction > 0 else 270)
        speed = WALK_SPEED * U
        phase = 0.0
        moved = 0.0
        hw = self.rig.hw
        # 隨機邊走邊種月光花／跌倒
        plant_at = (random.uniform(0.25, 0.75) * dist
                    if (events and self.on_plant and not self.platform and random.random() < PLANT_CHANCE) else -1)
        trip_at = random.uniform(0.2, 0.9) * dist if (events and random.random() < TRIP_CHANCE) else -1
        while moved < dist:
            if 0 <= plant_at <= moved:
                plant_at = -1
                yield from self.plant_here(direction)
                yield from self.turn_to(90 if direction > 0 else 270, 0.08)
            if 0 <= trip_at <= moved:
                self.stride = 0.0
                self.a["lean"] = 0.0
                yield from self.act_trip()
                return
            l, t, r, b = self.work
            nx = self.P[0] + speed * self.dt * direction
            if nx > r - hw or nx < l + hw:
                self.a["lean"] = 0.0
                self.stride = 0.0
                if not events:
                    break
                if self.platform and random.random() < 0.5:
                    yield from self.act_jump_down(direction)
                    return
                direction = -direction
                yield from self.turn_to(90 if direction > 0 else 270, 0.08)
                continue
            self.P[0] = nx
            moved += speed * self.dt
            phase += self.dt * 2 * math.pi * WALK_STEP_HZ
            # 點陣風：前傾用整數像素位移，不做小角度旋轉（避免鋸齒抖動）
            # 前後腳交替、前後手反向擺（Rig.compose_walk）；雙腳併攏時身體最高
            self.gait = phase
            self.stride = WALK_STRIDE
            self.a["lean"] = direction * 0.025 * U
            self.a["legs"] = 0.0
            self.a["head"] = math.cos(phase * 2) * 0.01 * U
            self.ground(abs(math.cos(phase)) * 0.016 * U)
            yield
        self.stride = 0.0
        for p in self.over(0.12):
            self.a["lean"] = 0.0
            self.ground()
            yield
        if face_front:
            yield from self.turn_to(0)

    def plant_here(self, direction=0):
        """停下來、轉正面蹲下種一朵月光花，再站起來。"""
        self.stride = 0.0
        self.a["lean"] = 0.0
        yield from self.turn_to(0, 0.08)
        # 蹲下
        for p in self.over(0.22):
            e = ease(p)
            self.sy = 1 - 0.2 * e
            self.sx = 1 + 0.1 * e
            self.a["head"] = 0.02 * self.U * e * (1 if direction >= 0 else -1)
            self.ground()
            yield
        # 拍拍土
        for p in self.over(0.5):
            self.a["legs"] = 0.0
            self.a["head"] = 0.02 * self.U * (1 if direction >= 0 else -1) + math.sin(p * 6 * math.pi) * 0.008 * self.U
            self.sy = 0.8 + 0.02 * math.sin(p * 6 * math.pi)
            self.ground()
            yield
        if self.on_plant:
            l, t, r, b = self.work
            off = (0.32 * self.U) * (1 if direction >= 0 else -1)
            self.on_plant(min(max(self.P[0] + off, l + 10), r - 10), b)
        for p in self.over(0.18):
            e = ease(p)
            self.sy = 0.8 + 0.2 * e
            self.sx = 1.1 - 0.1 * e
            self.a["head"] = 0.0
            self.ground()
            yield
        self.sx = self.sy = 1.0
        self.kick(0.5 * self.U, 0.6)

    def act_plant(self):
        yield from self.plant_here(random.choice([1, -1]))
        yield from self.act_idle(0.6, face=False)

    def act_spin(self, turns=None):
        turns = turns or random.choice([1, 1, 2])
        d = random.choice([1, -1])
        start = self.yaw
        dur = 0.8 * turns
        for p in self.over(dur):
            self.set_yaw(start + d * 360 * turns * ease(p))
            self.a["flare"] = 0.12 * math.sin(math.pi * p)
            self.ground(4 * 0.12 * self.U * p * (1 - p))
            yield
        self.set_yaw(start)
        self.a["flare"] = 0.0
        self.kick(0.6 * self.U)
        yield from self.act_idle(0.3, face=False)

    def act_bounce(self, heights=(0.75, 0.45, 0.22)):
        yield from self.crouch()
        for h in heights:
            v0 = math.sqrt(2 * self.G * h * self.U)
            impact, _ = yield from self.airborne(0, -v0)
            self.kick(impact)
        yield from self.settle(0.4)

    def act_frontflip(self):
        yield from self.turn_to(0)
        yield from self.crouch(0.2, 0.22)
        v0 = math.sqrt(2 * self.G * 1.3 * self.U)
        t_air = 2 * v0 / self.G

        def cb(T):
            p = min(1.0, T / (t_air * 0.9))
            phi = 360 * ease(p)
            view, vrot = FLIP_VIEWS[int(round(phi / 90.0)) % 4]
            self.view, self.view_rot = view, vrot
            self.squeeze_y = 0.55 + 0.45 * abs(math.cos(math.radians(2 * phi)))
            self.a["flare"] = 0.1 * math.sin(math.pi * p)

        impact, _ = yield from self.airborne(0, -v0, cb=cb)
        self.squeeze_y = 1.0
        self.a["flare"] = 0.0
        self.set_yaw(0)
        self.kick(impact)
        yield from self.settle(0.45)

    def act_somersault(self, direction=0):
        direction = direction or random.choice([1, -1])
        yield from self.turn_to(90 if direction > 0 else 270)
        yield from self.crouch(0.18, 0.2)
        v0 = math.sqrt(2 * self.G * 1.0 * self.U)
        t_air = 2 * v0 / self.G
        spin = direction * 360 / (t_air * 0.85)

        def cb(T):
            if abs(self.rot) >= 360:
                self.rot = 360.0 * direction
            self.a["legs"] = -direction * 0.03 * self.U * math.sin(math.pi * min(1, T / t_air))

        impact, _ = yield from self.airborne(direction * 0.55 * self.U, -v0, spin, cb)
        self.rot = wrap180(self.rot)
        self.a["legs"] = 0.0
        self.kick(impact)
        yield from self.settle(0.3)
        yield from self.turn_to(0)

    def act_hang(self, from_drag=False):
        U = self.U
        l, t, r, b = self.work
        target_y = t + self.rig.dh + 0.03 * U
        if not from_drag:
            yield from self.turn_to(0)
            yield from self.crouch(0.18, 0.15)
            vy = 0.0
            x0 = self.P[0]
            t0 = self.t
            while self.P[1] > target_y:
                vy = min(vy + 3.0 * U * self.dt, 2.4 * U)
                self.P[1] = max(target_y, self.P[1] - vy * self.dt)
                self.P[0] = x0 + math.sin((self.t - t0) * 4) * 0.04 * U
                self.a["wing"] = math.sin(self.t * 30) * 0.025 * U
                self.a["legs"] = math.sin(self.t * 7) * 0.012 * U
                yield
        # 翻成倒立
        r0 = wrap180(self.rot)
        target_rot = 180.0 if r0 >= 0 else -180.0
        y0 = self.P[1]
        for p in self.over(0.45):
            e = ease(p)
            self.rot = r0 + (target_rot - r0) * e
            self.P[1] = y0 + (target_y - y0) * e
            self.a["wing"] = math.sin(self.t * 30) * 0.025 * U
            yield
        self.rot = 180.0
        self.a["wing"] = 0.0
        fx, fy = self.P[0] + self.feet_vec()[0], self.P[1] + self.feet_vec()[1]
        for p in self.over(0.18):
            self.place_feet(fx, fy + (t - fy) * ease(p))
            yield
        anchor = (fx, t)
        self.kick(0.8 * U, 0.6)
        # 倒吊擺盪
        T = 0.0
        dur = random.uniform(5.0, 8.0)
        for p in self.over(dur):
            T += self.dt
            amp = 4 + 12 * math.exp(-T * 0.6)
            self.rot = 180 + amp * math.sin(T * 2 * math.pi / 1.5)
            self.a["legs"] = math.sin(T * 3.1) * 0.006 * U
            self.a["head"] = math.sin(T * 1.7) * 0.01 * U
            if 0.35 < p < 0.5:
                self.set_yaw(315)
            elif 0.55 < p < 0.7:
                self.set_yaw(45)
            else:
                self.set_yaw(0)
            self.place_feet(*anchor)
            yield
        self.set_yaw(0)
        # 放手：落下時半圈翻回正
        self.rot = 180.0
        fall_h = max(b - self.P[1], 1)
        t_fall = math.sqrt(2 * fall_h / self.G)
        spin = 180 / max(t_fall * 0.85, 0.15)

        def cb(T):
            if self.rot >= 360:
                self.rot = 360.0

        impact, _ = yield from self.airborne(0, 0, spin, cb)
        self.rot = wrap180(self.rot)
        self.kick(impact)
        yield from self.settle(0.35)

    def act_fall(self, vx, vy, spin, keep_rot=False):
        if not keep_rot:
            self.reset_pose()
        while True:
            impact, vx = yield from self.airborne(vx, vy, spin)
            self.kick(impact)
            if impact > 1.6 * self.U:
                vy, vx, spin = -impact * 0.42, vx * 0.7, spin * 0.5
            else:
                break
        yield from self.settle(0.4)
        yield from self.turn_to(0)

    # ---------------------------------------------------------- 系統：說話、粒子、視線、視窗平台
    def say(self, text, dur=None):
        self.speech = (text, self.t + (dur or 1.8 + 0.13 * len(text)))

    def spawn(self, kind, x, y, vx=0.0, vy=0.0, g=0.0, life=1.0):
        if len(self.particles) < 90:
            self.particles.append({"kind": kind, "x": x, "y": y, "vx": vx, "vy": vy, "g": g, "life": life,
                                   "age": 0.0, "ph": random.uniform(0, 6.28)})

    def update_particles(self, dt):
        keep = []
        for q in self.particles:
            q["age"] += dt
            if q["age"] > q["life"]:
                continue
            q["vy"] += q["g"] * dt
            q["x"] += q["vx"] * dt
            q["y"] += q["vy"] * dt
            if q["kind"] in ("bubble", "z"):
                q["x"] += math.sin(q["age"] * 5 + q["ph"]) * 0.06 * self.U * dt
            keep.append(q)
        self.particles = keep

    def update_look(self, dt):
        """視線跟著滑鼠：頭部位移；滑鼠離很遠時頭轉向斜側。"""
        tx = ty = 0.0
        hv = None
        ok = (self.look_enabled and self.cursor_pos is not None and not self.dragging and self.stride == 0
              and not self.sleeping and self.view == ("front", False) and abs(wrap180(self.rot)) < 3
              and self.squeeze_y == 1.0)
        if ok:
            U = self.U
            dx = self.cursor_pos[0] - self.P[0]
            dy = self.cursor_pos[1] - (self.P[1] - 0.3 * U)
            tx = max(-1.0, min(1.0, dx / (2.5 * U)))
            ty = max(-1.0, min(1.0, dy / (2.5 * U)))
            enter, leave = 0.9 * U, 0.6 * U
            if self.head_view == ("fl", False) and dx < -leave:
                hv = ("fl", False)
            elif self.head_view == ("fl", True) and dx > leave:
                hv = ("fl", True)
            elif dx < -enter:
                hv = ("fl", False)
            elif dx > enter:
                hv = ("fl", True)
        self.head_view = hv
        s = self.rig.s
        k = min(1.0, dt * 8)
        self.look[0] += (tx * 1.6 * s - self.look[0]) * k
        self.look[1] += (ty * 1.2 * s - self.look[1]) * k

    def update_platform(self):
        self.base_work = self.work_fn(self.P)
        self.work = self.base_work
        if not self.platform:
            return
        rect = self.win_rect_fn(self.platform["hwnd"]) if self.win_rect_fn else None
        bl, bt, br, bb = self.base_work
        if (rect is None or rect[2] - rect[0] < 0.6 * self.U or rect[1] < bt + 0.3 * self.U
                or rect[1] > bb - 0.3 * self.U):
            self.platform = None
            if not self.dragging:
                self.say("哇！", 1.0)
                self.run(self.act_idle(0.3, face=False))  # _chain 會先讓她掉下來
            return
        old = self.platform["rect"]
        dx, dy = rect[0] - old[0], rect[1] - old[1]
        if not self.dragging:
            self.P[0] += dx
            self.lastP[0] += dx
            self.lastP[1] += dy
        self.platform["rect"] = rect
        self.work = (rect[0], bt, rect[2], rect[1])

    # ---------------------------------------------------------- 互動動作
    def act_eat(self):
        U = self.U
        yield from self.turn_to(0)
        l, t, r, b = self.work
        d = 1 if (r - self.P[0]) > (self.P[0] - l) else -1
        fx = self.P[0] + d * 0.33 * U
        self.say("有點心！", 1.2)
        fy, vy, bounced = b - 1.3 * U, 0.0, False
        while True:  # 糰子從天上掉下來
            vy += self.G * self.dt
            fy += vy * self.dt
            if fy >= self.work[3]:
                fy = self.work[3]
                if not bounced and vy > 0.6 * U:
                    vy, bounced = -vy * 0.3, True
                else:
                    break
            self.props["food"] = (draw_dango(0), fx, fy, "front")
            self.ground()
            yield
        yield from self.turn_to(90 if d > 0 else 270)
        for k in range(3):
            for p in self.over(0.2):
                self.a["lean"] = d * 0.05 * U * ease(p)
                self.a["head"] = d * 0.03 * U * ease(p)
                self.ground()
                yield
            self.props["food"] = (draw_dango(k + 1), fx, self.work[3], "front")
            for _ in range(4):
                self.spawn("crumb", fx, self.work[3] - 0.15 * U, random.uniform(-0.6, 0.6) * U,
                           -random.uniform(0.4, 1.0) * U, 3 * U, 0.6)
            for p in self.over(0.5):
                self.a["lean"] = d * 0.015 * U
                self.a["head"] = d * 0.012 * U + math.sin(p * 4 * math.pi) * 0.01 * U
                self.ground()
                yield
        self.props.pop("food", None)
        self.a["lean"] = self.a["head"] = 0.0
        if self.care:
            self.care.add("hunger", 35)
            self.care.add("mood", 4)
        yield from self.turn_to(0)
        self.say(random.choice(LINES["eat"]))
        for _ in range(3):
            self.spawn("heart", self.P[0] + random.uniform(-0.25, 0.25) * U, self.P[1] - 0.4 * U,
                       0, -0.4 * U, 0, 1.2)
        yield from self.act_bounce((0.3, 0.12))

    def update_pillow(self):
        sxT, syT = self.total_scale()
        hx, hy = rot2(0, -0.62 * self.rig.dh * syT, self.rot)
        self.props["pillow"] = (PILLOW, self.P[0] + hx, self.work[3], "front")  # 頭陷進枕頭

    def act_sleep(self, max_dur=40.0):
        yield from self.turn_to(0)
        self.say("呼啊…想睡了。")
        for p in self.over(0.7):  # 打呵欠
            self.sy = 1 + 0.06 * math.sin(math.pi * p)
            self.sx = 1 - 0.04 * math.sin(math.pi * p)
            self.ground()
            yield
        self.sx = self.sy = 1.0
        for p in self.over(0.5):  # 躺下（頭在左邊，枕著枕頭）
            self.rot = -90 * ease(p)
            self.ground()
            self.update_pillow()
            yield
        self.sleeping, self.wake_req = True, False
        T = zt = 0.0
        while T < max_dur and not self.wake_req and not (self.care and self.care.v["energy"] >= 100):
            T += self.dt
            zt += self.dt
            if zt > 1.1:
                zt = 0.0
                hx, hy = rot2(0, -0.8 * self.rig.dh, self.rot)
                self.spawn("z", self.P[0] + hx, self.P[1] + hy - 0.1 * self.U, 0.08 * self.U, -0.3 * self.U, 0, 1.7)
            self.ground()
            self.update_pillow()
            yield
        self.sleeping = False
        self.say("嗯…？" if self.wake_req else "…早安。")
        self.wake_req = False
        for p in self.over(0.5):
            self.rot = -90 * (1 - ease(p))
            self.ground()
            self.update_pillow()
            yield
        self.props.pop("pillow", None)
        self.rot = 0.0
        yield from self.turn_to(0)

    def act_bath(self):
        U = self.U
        yield from self.turn_to(0)
        self.say("洗澡時間～")
        bt = 0.0
        for p in self.over(3.0):
            self.props["foam"] = (FOAM, self.P[0], self.P[1] - self.rig.dh * 0.62, "front")
            self.a["head"] = math.sin(self.t * 10) * 0.02 * U
            self.squeeze_x = 1 + 0.04 * math.sin(self.t * 14)
            bt += self.dt
            if bt > 0.12:
                bt = 0.0
                self.spawn("bubble", self.P[0] + random.uniform(-0.35, 0.35) * U,
                           self.P[1] + random.uniform(-0.3, 0.3) * U, 0, -random.uniform(0.25, 0.55) * U, 0,
                           random.uniform(1.0, 1.8))
            self.ground()
            yield
        self.squeeze_x = 1.0
        self.a["head"] = 0.0
        self.props.pop("foam", None)
        self.say("甩一甩——", 1.2)
        start = self.yaw
        for p in self.over(0.8):
            self.set_yaw(start + 360 * ease(p))
            if random.random() < 0.6:
                ang = random.uniform(0, 2 * math.pi)
                self.spawn("drop", self.P[0], self.P[1] - 0.2 * U, math.cos(ang) * 1.2 * U,
                           -abs(math.sin(ang)) * 1.0 * U, 3 * U, 0.6)
            self.ground()
            yield
        self.set_yaw(start)
        for _ in range(6):
            self.spawn("spark", self.P[0] + random.uniform(-0.4, 0.4) * U, self.P[1] + random.uniform(-0.45, 0.3) * U,
                       0, -0.1 * U, 0, 1.0)
        if self.care:
            self.care.v["clean"] = 100.0
            self.care.add("mood", 5)
        self.say("香香的。")
        yield from self.act_idle(0.8, face=False)

    def act_trip(self):
        U = self.U
        if self.view not in self.rig.legs:
            yield from self.turn_to(random.choice([90, 270]))
        d = self.facing()
        self.say("哇——", 1.0)
        for p in self.over(0.3):  # 往前撲倒
            self.rot = d * 90 * ease(p)
            self.P[0] += d * 0.5 * U * self.dt
            self.ground(0.1 * U * math.sin(math.pi * p))
            yield
        self.rot = d * 90.0
        self.kick(1.4 * U)
        for _ in range(6):
            self.spawn("dust", self.P[0] + d * 0.3 * U + random.uniform(-0.25, 0.25) * U, self.work[3] - 2,
                       random.uniform(-0.4, 0.4) * U, -random.uniform(0.2, 0.5) * U, 1.5 * U, 0.6)
        if self.care:
            self.care.add("mood", -4)
        for _ in self.over(1.1):
            self.ground()
            yield
        self.say(random.choice(LINES["trip"]))
        yield from self.settle(0.45)
        yield from self.turn_to(0)

    def act_climb(self):
        """走到某個視窗旁，沿著視窗邊緣爬上去，站在視窗頂端。"""
        U = self.U
        if self.platform or not self.windows_fn:
            return
        l, t, r, b = self.base_work
        hw = self.rig.hw
        cands = []
        for hwnd, (wl, wt, wr, wb) in self.windows_fn():
            if wr - wl < 1.4 * U or wt < t + 1.15 * U or wt > b - 0.9 * U:
                continue
            for side, edge in ((-1, wl), (1, wr)):
                ax = edge + side * 0.2 * U
                if l + hw <= ax <= r - hw:
                    cands.append((abs(ax - self.P[0]), hwnd, side))
        if not cands:
            self.say("沒有可以爬的窗戶…")
            yield from self.act_idle(1.0, face=False)
            return
        cands.sort(key=lambda c: c[0])
        _, hwnd, side = random.choice(cands[:3])
        self.say("爬上去看看。")

        def edge_x():
            rc = self.win_rect_fn(hwnd)
            if rc is None:
                return None, None
            return (rc[0] if side < 0 else rc[2]), rc

        ex, rect = edge_x()
        if ex is None:
            return
        ax = ex + side * 0.2 * U
        if abs(ax - self.P[0]) > 2:
            yield from self.act_walk(1 if ax > self.P[0] else -1, abs(ax - self.P[0]), face_front=False, events=False)
        yield from self.turn_to(180)
        fy = self.work[3]
        x0 = self.P[0]
        phase = 0.0
        while True:  # 爬
            ex, rect = edge_x()
            if ex is None:
                self.say("哇！", 1.0)
                yield from self.act_fall(0, 0, 0, keep_rot=True)
                return
            xc = ex + side * 0.06 * U
            fy -= CLIMB_SPEED * U * self.dt * (0.6 + 0.4 * abs(math.sin(phase)))
            phase += self.dt * 2 * math.pi * 1.4
            self.a["legs"] = math.sin(phase) * 0.025 * U
            self.a["head"] = math.sin(phase) * 0.012 * U
            x = x0 + (xc - x0) * min(1.0, (self.work[3] - fy) / (0.3 * U))
            if fy <= rect[1]:
                break
            self.place_feet(x + math.sin(phase) * 0.01 * U, fy)
            yield
        self.a["legs"] = self.a["head"] = 0.0
        tx = ex - side * 0.45 * U
        for p in self.over(0.35):  # 翻上視窗頂
            ex2, rect = edge_x()
            if ex2 is None:
                break
            self.place_feet(xc + (tx - xc) * ease(p), rect[1] - math.sin(math.pi * p) * 0.18 * U)
            yield
        ex, rect = edge_x()
        if ex is None:
            yield from self.act_fall(0, 0, 0, keep_rot=True)
            return
        self.platform = {"hwnd": hwnd, "rect": rect}
        self.work = (rect[0], self.base_work[1], rect[2], rect[1])
        self.ground()
        self.kick(0.8 * U)
        yield from self.turn_to(0)
        self.say("爬上來了。")
        yield from self.act_idle(0.8, face=False)

    def act_jump_down(self, direction=0):
        if not self.platform:
            return
        rect = self.platform["rect"]
        hw = self.rig.hw
        if direction == 0:
            direction = 1 if (rect[2] - self.P[0]) < (self.P[0] - rect[0]) else -1
            edge = rect[2] - hw if direction > 0 else rect[0] + hw
            if abs(edge - self.P[0]) > 2:
                yield from self.act_walk(direction, abs(edge - self.P[0]), face_front=False, events=False)
        yield from self.turn_to(90 if direction > 0 else 270, 0.06)
        self.say("跳下去囉。", 1.2)
        yield from self.crouch(0.16, 0.18)
        self.platform = None
        self.work = self.base_work
        impact, _ = yield from self.airborne(direction * 0.6 * self.U, -1.6 * self.U)
        self.kick(impact)
        yield from self.settle(0.35)
        yield from self.turn_to(0)

    # ---------------------------------------------------------- drag
    def grab(self, mx, my):
        self.action = None
        self.dragging = True
        self.queue.clear()
        self.reset_pose()
        self.platform = None
        dx, dy = self.P[0] - mx, self.P[1] - my
        self.grab_o = rot2(dx, dy, -self.rot)
        self.mouse = (mx, my)
        self.m_prev = (mx, my)
        self.m_v = (0.0, 0.0)
        self.rot_v = 0.0

    def drag_to(self, mx, my):
        self.mouse = (mx, my)

    def drag_step(self):
        dt = self.dt
        mx, my = self.mouse
        nvx, nvy = (mx - self.m_prev[0]) / dt, (my - self.m_prev[1]) / dt
        self.m_prev = (mx, my)
        a = 0.5
        ovx, ovy = self.m_v
        self.m_v = (ovx + (nvx - ovx) * a, ovy + (nvy - ovy) * a)
        ax = max(-9000, min(9000, (self.m_v[0] - ovx) / dt))
        ay = max(-9000, min(9000, (self.m_v[1] - ovy) / dt))
        ox, oy = self.grab_o
        L = max(math.hypot(ox, oy), 0.15 * self.U)
        wx, wy = rot2(ox, oy, self.rot)
        beta = math.radians(wrap180(math.degrees(math.atan2(wy, wx)) - 90))
        g_eff = self.G - ay
        acc = (-(g_eff / L) * math.sin(beta) + (ax / L) * math.cos(beta)) * 57.2958 - 3.5 * self.rot_v
        self.rot_v += acc * dt
        self.rot_v = max(-1500, min(1500, self.rot_v))
        self.rot += self.rot_v * dt
        wx, wy = rot2(ox, oy, self.rot)
        self.P[0], self.P[1] = mx + wx, my + wy
        self.a["legs"] = math.sin(self.t * 6) * 0.015 * self.U
        self.a["wing"] = math.sin(self.t * 24) * 0.012 * self.U

    def release(self):
        if not self.dragging:
            return
        self.dragging = False
        U = self.U
        vx = max(-4 * U, min(4 * U, self.m_v[0]))
        vy = max(-5 * U, min(4 * U, self.m_v[1]))
        spin = max(-720, min(720, self.rot_v * 0.6 + vx * 0.15))
        self.a["legs"] = self.a["wing"] = 0.0
        lo, _ = self.extent()
        if self.P[1] + lo - self.work[1] < 0.15 * U and abs(vy) < 1.5 * U:
            self.action = self.act_hang(from_drag=True)
        else:
            self.action = self.act_fall(vx, vy, spin, keep_rot=True)


# ------------------------------------------------------------------ Win32 window
def run_app():
    import ctypes
    import ctypes.wintypes as wt
    import tkinter as tk

    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)

    class POINT(ctypes.Structure):
        _fields_ = [("x", wt.LONG), ("y", wt.LONG)]

    class SIZE(ctypes.Structure):
        _fields_ = [("cx", wt.LONG), ("cy", wt.LONG)]

    class BLENDFUNCTION(ctypes.Structure):
        _fields_ = [("BlendOp", ctypes.c_ubyte), ("BlendFlags", ctypes.c_ubyte),
                    ("SourceConstantAlpha", ctypes.c_ubyte), ("AlphaFormat", ctypes.c_ubyte)]

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [("biSize", wt.DWORD), ("biWidth", wt.LONG), ("biHeight", wt.LONG),
                    ("biPlanes", wt.WORD), ("biBitCount", wt.WORD), ("biCompression", wt.DWORD),
                    ("biSizeImage", wt.DWORD), ("biXPelsPerMeter", wt.LONG), ("biYPelsPerMeter", wt.LONG),
                    ("biClrUsed", wt.DWORD), ("biClrImportant", wt.DWORD)]

    class BITMAPINFO(ctypes.Structure):
        _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wt.DWORD * 3)]

    class MONITORINFO(ctypes.Structure):
        _fields_ = [("cbSize", wt.DWORD), ("rcMonitor", wt.RECT), ("rcWork", wt.RECT), ("dwFlags", wt.DWORD)]

    user32.GetDC.argtypes = [wt.HWND]
    user32.GetDC.restype = wt.HDC
    gdi32.CreateCompatibleDC.argtypes = [wt.HDC]
    gdi32.CreateCompatibleDC.restype = wt.HDC
    gdi32.CreateDIBSection.argtypes = [wt.HDC, ctypes.POINTER(BITMAPINFO), wt.UINT,
                                       ctypes.POINTER(ctypes.c_void_p), wt.HANDLE, wt.DWORD]
    gdi32.CreateDIBSection.restype = wt.HBITMAP
    gdi32.SelectObject.argtypes = [wt.HDC, wt.HGDIOBJ]
    gdi32.SelectObject.restype = wt.HGDIOBJ
    gdi32.DeleteObject.argtypes = [wt.HGDIOBJ]
    user32.UpdateLayeredWindow.argtypes = [wt.HWND, wt.HDC, ctypes.POINTER(POINT), ctypes.POINTER(SIZE),
                                           wt.HDC, ctypes.POINTER(POINT), wt.DWORD,
                                           ctypes.POINTER(BLENDFUNCTION), wt.DWORD]
    user32.UpdateLayeredWindow.restype = wt.BOOL
    user32.GetWindowLongPtrW.argtypes = [wt.HWND, ctypes.c_int]
    user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
    user32.SetWindowLongPtrW.argtypes = [wt.HWND, ctypes.c_int, ctypes.c_ssize_t]
    user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
    user32.MonitorFromPoint.argtypes = [POINT, wt.DWORD]
    user32.MonitorFromPoint.restype = wt.HMONITOR
    user32.GetMonitorInfoW.argtypes = [wt.HMONITOR, ctypes.POINTER(MONITORINFO)]
    user32.GetCursorPos.argtypes = [ctypes.POINTER(POINT)]
    user32.SetWindowPos.argtypes = [wt.HWND, wt.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                    ctypes.c_int, wt.UINT]

    GWL_EXSTYLE = -20
    WS_EX_LAYERED, WS_EX_TOOLWINDOW, WS_EX_TOPMOST = 0x80000, 0x80, 0x8
    ULW_ALPHA = 2
    HWND_TOPMOST = wt.HWND(-1)

    def work_area(pt):
        mon = user32.MonitorFromPoint(POINT(int(pt[0]), int(pt[1])), 2)
        mi = MONITORINFO()
        mi.cbSize = ctypes.sizeof(MONITORINFO)
        user32.GetMonitorInfoW(mon, ctypes.byref(mi))
        w = mi.rcWork
        return (w.left, w.top, w.right, w.bottom)

    def cursor():
        p = POINT()
        user32.GetCursorPos(ctypes.byref(p))
        return p.x, p.y

    gdi32.DeleteDC.argtypes = [wt.HDC]
    screen_dc = user32.GetDC(None)
    blend = BLENDFUNCTION(0, 0, 255, 1)

    class LWin:
        """逐像素半透明的 Tk 視窗（UpdateLayeredWindow）。"""

        def __init__(self, win):
            win.overrideredirect(True)
            win.geometry("8x8+-3000+-3000")
            win.update_idletasks()
            win.attributes("-topmost", True)
            win.update()
            self.win = win
            self.hwnd = int(win.wm_frame(), 16)
            ex = user32.GetWindowLongPtrW(self.hwnd, GWL_EXSTYLE)
            user32.SetWindowLongPtrW(self.hwnd, GWL_EXSTYLE, ex | WS_EX_LAYERED | WS_EX_TOOLWINDOW | WS_EX_TOPMOST)
            self.dc = gdi32.CreateCompatibleDC(screen_dc)
            self.size = (0, 0)
            self.bits = None
            self.bmp = None

        def _alloc(self, w, h):
            bmi = BITMAPINFO()
            hd = bmi.bmiHeader
            hd.biSize = ctypes.sizeof(BITMAPINFOHEADER)
            hd.biWidth, hd.biHeight = w, -h
            hd.biPlanes, hd.biBitCount = 1, 32
            bits = ctypes.c_void_p()
            bmp = gdi32.CreateDIBSection(self.dc, ctypes.byref(bmi), 0, ctypes.byref(bits), None, 0)
            gdi32.SelectObject(self.dc, bmp)
            if self.bmp:
                gdi32.DeleteObject(self.bmp)
            self.size, self.bits, self.bmp = (w, h), bits, bmp
            self.win.geometry(f"{w}x{h}")

        def push(self, img, x, y, scale=1):
            """img 為原生點陣；在原生尺寸做預乘 alpha，再以整數倍複製像素放大。"""
            a = np.asarray(img, dtype=np.uint8)
            al = a[..., 3:4].astype(np.uint16)
            rgb = ((a[..., :3].astype(np.uint16) * al + 127) // 255).astype(np.uint8)
            out = np.empty_like(a)
            out[..., 0] = rgb[..., 2]
            out[..., 1] = rgb[..., 1]
            out[..., 2] = rgb[..., 0]
            out[..., 3] = a[..., 3]
            if scale != 1:
                out = np.repeat(np.repeat(out, scale, 0), scale, 1)
            out = np.ascontiguousarray(out)
            h, w = out.shape[:2]
            if (w, h) != self.size:
                self._alloc(w, h)
            ctypes.memmove(self.bits, out.ctypes.data, out.nbytes)
            user32.UpdateLayeredWindow(self.hwnd, screen_dc, ctypes.byref(POINT(int(x), int(y))),
                                       ctypes.byref(SIZE(w, h)), self.dc, ctypes.byref(POINT(0, 0)), 0,
                                       ctypes.byref(blend), ULW_ALPHA)

        def raise_top(self):
            user32.SetWindowPos(self.hwnd, HWND_TOPMOST, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010)

        def destroy(self):
            try:
                self.win.destroy()
            finally:
                if self.bmp:
                    gdi32.DeleteObject(self.bmp)
                gdi32.DeleteDC(self.dc)

    from PIL import ImageTk

    # ---- 視窗列舉（爬視窗用）
    dwmapi = ctypes.WinDLL("dwmapi")
    dwmapi.DwmGetWindowAttribute.argtypes = [wt.HWND, wt.DWORD, ctypes.c_void_p, wt.DWORD]
    user32.IsWindow.argtypes = [wt.HWND]
    user32.IsWindowVisible.argtypes = [wt.HWND]
    user32.IsIconic.argtypes = [wt.HWND]
    user32.GetWindowTextLengthW.argtypes = [wt.HWND]
    user32.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
    user32.WindowFromPoint.argtypes = [POINT]
    user32.WindowFromPoint.restype = wt.HWND
    user32.GetAncestor.argtypes = [wt.HWND, wt.UINT]
    user32.GetAncestor.restype = wt.HWND
    user32.GetWindowRect.argtypes = [wt.HWND, ctypes.POINTER(wt.RECT)]
    EnumWindowsProc = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    user32.EnumWindows.argtypes = [EnumWindowsProc, wt.LPARAM]
    my_pid = os.getpid()

    def win_rect(hwnd):
        if not user32.IsWindow(hwnd) or not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd):
            return None
        cloaked = wt.DWORD(0)
        dwmapi.DwmGetWindowAttribute(hwnd, 14, ctypes.byref(cloaked), 4)
        if cloaked.value:
            return None
        r = wt.RECT()
        if dwmapi.DwmGetWindowAttribute(hwnd, 9, ctypes.byref(r), ctypes.sizeof(r)) != 0:
            user32.GetWindowRect(hwnd, ctypes.byref(r))
        return (r.left, r.top, r.right, r.bottom)

    def top_visible(hwnd, r):
        """視窗頂端中間是不是真的看得到（沒有被別的視窗蓋住）。"""
        x, y = (r[0] + r[2]) // 2, r[1] + 4
        h = user32.WindowFromPoint(POINT(x, y))
        return h and user32.GetAncestor(h, 2) == hwnd

    def list_windows():
        out = []

        def cb(h, _l):
            if user32.GetWindowTextLengthW(h) == 0:
                return True
            pid = wt.DWORD()
            user32.GetWindowThreadProcessId(h, ctypes.byref(pid))
            if pid.value == my_pid:
                return True
            if user32.GetWindowLongPtrW(h, GWL_EXSTYLE) & WS_EX_TOOLWINDOW:
                return True
            r = win_rect(h)
            if r and r[2] - r[0] > 60 and r[3] - r[1] > 60 and top_visible(h, r):
                out.append((h, r))
            return True

        user32.EnumWindows(EnumWindowsProc(cb), 0)
        return out

    # ---- 主角
    root = tk.Tk()
    root.title("夢境神明 L2D 桌寵")
    # 所有視窗（山谷、對話框）的圖示都換成月光花
    icons = [ImageTk.PhotoImage(moonflower_icon(n), master=root) for n in (16, 32, 48, 64)]
    root.iconphoto(True, *icons)
    root._moonflower_icons = icons
    pet_win = LWin(root)

    data_dir = Path(os.environ.get("APPDATA", str(ROOT))) / "DreamGodL2D"
    state = {"press": None, "dragged": False, "skip_release": False, "last": time.perf_counter(),
             "topmost_t": 0.0, "garden_t": 0.0, "home_t": 0.0}
    sprites = build_pixel_sprites()
    rig = Rig(SCALE, sprites)
    pet = Pet(rig, work_area)
    pet.care = Care(data_dir / "state.json")
    pet.windows_fn = list_windows
    pet.win_rect_fn = win_rect

    # ---- 月光花園
    save_path = data_dir / "flowers.json"

    class Garden:
        def __init__(self):
            self.items: list[dict] = []
            try:
                for d in json.loads(save_path.read_text(encoding="utf-8")):
                    self.add(float(d["x"]), float(d["floor"]), float(d["t0"]), save=False)
            except Exception:
                pass

        def save(self):
            try:
                save_path.parent.mkdir(parents=True, exist_ok=True)
                data = [{"x": it["x"], "floor": it["floor"], "t0": it["t0"]} for it in self.items]
                save_path.write_text(json.dumps(data), encoding="utf-8")
            except Exception:
                pass

        def add(self, x, floor, t0=None, save=True):
            while len(self.items) >= MAX_FLOWERS:
                self.remove(self.items[0], save=False)
            it = {"x": x, "floor": floor, "t0": t0 if t0 is not None else time.time(), "key": None,
                  "phase": random.uniform(0, 6.28)}
            it["win"] = LWin(tk.Toplevel(root))
            it["win"].win.bind("<ButtonPress-1>", lambda _e, it=it: self.remove(it))
            self.items.append(it)
            pet_win.raise_top()
            if save:
                self.save()

        def remove(self, it, save=True):
            if it in self.items:
                self.items.remove(it)
                it["win"].destroy()
                if save:
                    self.save()

        def clear(self):
            for it in list(self.items):
                self.remove(it, save=False)
            self.save()

        def update(self, t):
            s = SCALE
            night = is_night()
            now = time.time()
            for it in self.items:
                st = flower_stage(now - it["t0"])
                sway = int(round(math.sin(t * 1.3 + it["phase"]) * 1.2)) if st >= 2 else 0
                glow = round((0.75 + 0.25 * math.sin(t * 2.2 + it["phase"])) * 4) / 4 if (night and st == 4) else 0.0
                key = (st, sway, glow)
                if key == it["key"]:
                    continue
                it["key"] = key
                it["win"].push(draw_moonflower(st, sway, glow), it["x"] - FLOWER_W * s / 2,
                               it["floor"] - FLOWER_H * s, s)

    garden = Garden()
    pet.on_plant = garden.add

    # ---- 說話泡泡
    bubble = LWin(tk.Toplevel(root))
    bub = {"text": None, "img": None, "shown": False}
    EMPTY = Image.new("RGBA", (1, 1), (0, 0, 0, 0))

    def update_bubble():
        sp = pet.speech
        if sp and pet.t > sp[1]:
            pet.speech = sp = None
        if sp is None:
            if bub["shown"]:
                bubble.push(EMPTY, -3000, -3000)
                bub["shown"], bub["text"] = False, None
            return
        if sp[0] != bub["text"]:
            bub["text"], bub["img"] = sp[0], render_bubble(sp[0])
        img = bub["img"]
        w, h = img.width * SCALE, img.height * SCALE
        l, t, r, b = pet.base_work
        x = min(max(pet.P[0] - w / 2, l), r - w)
        y = max(pet.P[1] + pet.extent()[0] - h + 4, t)
        bubble.push(img, x, y, SCALE)
        if not bub["shown"]:
            bubble.raise_top()
        bub["shown"] = True

    # ---- 動作
    actions = {
        "eat": pet.act_eat, "bath": pet.act_bath, "sleep": pet.act_sleep, "climb": pet.act_climb,
        "bounce": pet.act_bounce, "frontflip": pet.act_frontflip, "spin": lambda: pet.act_spin(1),
        "plant": pet.act_plant, "hang": pet.act_hang, "walk": pet.act_walk, "trip": pet.act_trip,
        "jump_down": pet.act_jump_down, "look": pet.act_look, "somersault": pet.act_somersault,
        "walk_l": lambda: pet.act_walk(-1, 4 * pet.U), "walk_r": lambda: pet.act_walk(1, 4 * pet.U),
    }

    def do_action(name):
        if name == "wake":
            if pet.sleeping:
                pet.wake_req = True
            else:
                pet.say("我醒著喔。")
            return
        if name == "sleep" and pet.sleeping:
            return
        if name == "jump_down" and not pet.platform:
            pet.say("我在地上喔。")
            return
        if name == "climb" and pet.platform:
            pet.say("已經在上面了。")
            return
        pet.run(actions[name]())

    def talk(text):
        reply, act = respond(text)
        pet.say(reply)
        if pet.care:
            pet.care.add("mood", 1)
        if act:
            root.after(900, lambda: do_action(act))

    # ---- 跟她說話（小對話框）
    chat = {"win": None}

    def open_chat():
        if chat["win"] is not None and chat["win"].winfo_exists():
            chat["win"].deiconify()
            chat["win"].lift()
            return
        w = tk.Toplevel(root)
        w.title("跟她說話")
        w.attributes("-topmost", True)
        w.configure(bg="#0c0b14")
        w.resizable(False, False)
        e = tk.Entry(w, width=26, font=("Microsoft JhengHei UI", 12), bg="#1b1828", fg="#eeeaff",
                     insertbackground="#eeeaff", relief="flat")
        e.pack(side="left", padx=8, pady=8, ipady=4)

        def send(_e=None):
            text = e.get().strip()
            e.delete(0, "end")
            if text:
                talk(text)

        e.bind("<Return>", send)
        tk.Button(w, text="說", command=send, bg="#2a2540", fg="#eeeaff", activebackground="#3a3456",
                  activeforeground="#ffffff", relief="flat", padx=10).pack(side="left", padx=(0, 8))
        l, t, r, b = pet.base_work
        w.geometry(f"+{int(min(max(pet.P[0] - 160, l), r - 340))}+{int(max(pet.P[1] - 2.2 * pet.U, t))}")
        e.focus_set()
        chat["win"] = w

    # ---- 無夢之夢・月光花山谷（背景與照顧面板）
    HS = 2  # 山谷畫面放大倍率
    VW, VH = 200, 125
    home = {"win": None, "canvas": None, "photo": None}
    bar_colors = {"hunger": (250, 190, 206), "clean": (150, 200, 255), "mood": (255, 150, 182),
                  "energy": (206, 226, 168)}

    def open_home():
        if home["win"] is not None and home["win"].winfo_exists():
            home["win"].deiconify()
            home["win"].lift()
            return
        w = tk.Toplevel(root)
        w.title("無夢之夢・月光花山谷")
        w.configure(bg="#06060a")
        w.resizable(False, False)
        cv = tk.Canvas(w, width=VW * HS, height=VH * HS, highlightthickness=0, bg="#000000")
        cv.pack()
        btns = tk.Frame(w, bg="#06060a")
        btns.pack(fill="x", padx=4, pady=(4, 1))
        for i, (label, act) in enumerate((("餵食", "eat"), ("洗澡", "bath"), ("睡覺", "sleep"), ("叫醒", "wake"),
                                          ("爬視窗", "climb"), ("跳下來", "jump_down"), ("種花", "plant"),
                                          ("跌倒", "trip"))):
            tk.Button(btns, text=label, command=lambda a=act: do_action(a), bg="#17142a", fg="#e8e4ff",
                      activebackground="#2c2840", activeforeground="#ffffff", relief="flat", pady=0,
                      font=("Microsoft JhengHei UI", 9)).grid(row=i // 4, column=i % 4, padx=1, pady=1, sticky="ew")
        for c in range(4):
            btns.grid_columnconfigure(c, weight=1)
        row = tk.Frame(w, bg="#06060a")
        row.pack(fill="x", padx=4, pady=(1, 5))
        e = tk.Entry(row, width=10, font=("Microsoft JhengHei UI", 10), bg="#15131f", fg="#eeeaff",
                     insertbackground="#eeeaff", relief="flat")
        e.pack(side="left", fill="x", expand=True, ipady=2)

        def send(_e=None):
            text = e.get().strip()
            e.delete(0, "end")
            if text:
                talk(text)

        e.bind("<Return>", send)
        tk.Button(row, text="說話", command=send, bg="#2a2540", fg="#eeeaff", activebackground="#3a3456",
                  activeforeground="#ffffff", relief="flat", padx=6, pady=0,
                  font=("Microsoft JhengHei UI", 9)).pack(side="left", padx=(4, 0))

        def close():
            w.destroy()
            home["win"] = None

        w.protocol("WM_DELETE_WINDOW", close)
        home.update(win=w, canvas=cv)
        render_home()

    def render_home():
        if home["win"] is None:
            return
        t = pet.t
        bg = draw_valley(t, VW, VH)
        # 她站在山谷中央（同一套點陣與參數：呼吸、頭髮物理）
        p = pet.params()
        p.update(gait=0.0, stride=0.0, look_x=0.0, look_y=0.0, head_view=None, lean=0.0, legs=0.0)
        if pet.sleeping:
            img = rig.render(("front", False), p, -90, 1, 1)
            ox, oy = VW // 2 - WIN_N // 2, int(VH * 0.86) - WIN_N // 2 - int(rig.hw / rig.s * 0.9)
        else:
            img = rig.render(("front", False), p, 0, 1, 1)
            ox, oy = VW // 2 - WIN_N // 2, int(VH * 0.86) - WIN_N // 2 - int(rig.df / rig.s)
        bg.alpha_composite(img, (ox, max(oy, 0))) if oy >= 0 else bg.paste(img, (ox, oy), img)
        d = ImageDraw.Draw(bg)
        d.fontmode = "1"
        font = pixel_font(11)
        # 狀態面板
        d.rectangle((3, 3, 74, 58), fill=(8, 8, 16, 255), outline=(60, 56, 92, 255))
        for i, k in enumerate(CARE_KEYS):
            y = 6 + i * 13
            d.text((6, y), CARE_NAMES[k], font=font, fill=(232, 228, 255, 255))
            d.rectangle((32, y + 3, 70, y + 8), fill=(30, 28, 46, 255))
            v = pet.care.v[k] if pet.care else 0
            if v > 0:
                d.rectangle((32, y + 3, 32 + int(38 * v / 100), y + 8), fill=bar_colors[k] + (255,))
        # 說話泡泡
        if pet.speech:
            bb = render_bubble(pet.speech[0])
            bg.alpha_composite(bb, (max(0, min(VW - bb.width, VW // 2 - bb.width // 2)),
                                    max(0, oy + int(WIN_N / 2 - rig.dh / rig.s) - bb.height)))
        photo = ImageTk.PhotoImage(bg.resize((VW * HS, VH * HS), Image.NEAREST))
        cv = home["canvas"]
        cv.delete("all")
        cv.create_image(0, 0, anchor="nw", image=photo)
        home["photo"] = photo

    # ---- 滑鼠
    def on_press(_e):
        state["press"] = cursor()
        state["dragged"] = False

    def on_motion(_e):
        if state["press"] is None:
            return
        mx, my = cursor()
        if not state["dragged"]:
            px, py = state["press"]
            if abs(mx - px) + abs(my - py) < 5:
                return
            state["dragged"] = True
            pet.grab(px, py)
            pet.say("哇，被抓起來了。", 1.4)
        pet.drag_to(mx, my)

    def on_release(_e):
        state["press"] = None
        if state["dragged"]:
            pet.release()
        elif state["skip_release"]:
            state["skip_release"] = False
        elif pet.sleeping:
            pet.wake_req = True
        else:
            pet.say(random.choice(LINES["click"]))
            if pet.care:
                pet.care.add("mood", 2)
            pet.spawn("heart", pet.P[0], pet.P[1] - 0.45 * pet.U, 0, -0.35 * pet.U, 0, 1.0)
            pet.run(pet.act_bounce((0.3, 0.12)))
        state["dragged"] = False

    def on_double(_e):
        state["skip_release"] = True
        open_home()

    # ---- 右鍵選單
    menu = tk.Menu(root, tearoff=0)
    auto_var = tk.BooleanVar(value=True)
    look_var = tk.BooleanVar(value=True)

    def do(name):
        return lambda: do_action(name)

    menu.add_command(label="打開月光花山谷", command=open_home)
    menu.add_command(label="跟她說話…", command=open_chat)
    menu.add_separator()
    menu.add_command(label="餵食", command=do("eat"))
    menu.add_command(label="洗澡", command=do("bath"))
    menu.add_command(label="睡覺", command=do("sleep"))
    menu.add_command(label="叫醒", command=do("wake"))
    menu.add_command(label="爬視窗", command=do("climb"))
    menu.add_command(label="從視窗跳下來", command=do("jump_down"))
    menu.add_command(label="跌倒", command=do("trip"))
    menu.add_separator()
    more = tk.Menu(menu, tearoff=0)
    for label, name in (("往左走", "walk_l"), ("往右走", "walk_r"), ("轉一圈", "spin"), ("東張西望", "look"),
                        ("彈跳", "bounce"), ("前空翻", "frontflip"), ("側翻", "somersault"), ("倒吊", "hang"),
                        ("種月光花", "plant")):
        more.add_command(label=label, command=do(name))
    menu.add_cascade(label="更多動作", menu=more)
    menu.add_command(label="清除所有花", command=lambda: garden.clear())
    menu.add_separator()

    def toggle_auto():
        pet.auto = auto_var.get()

    def toggle_look():
        pet.look_enabled = look_var.get()

    def quit_app():
        garden.save()
        if pet.care:
            pet.care.save()
        root.destroy()

    menu.add_checkbutton(label="視線跟著滑鼠", variable=look_var, command=toggle_look)
    menu.add_checkbutton(label="自動行動", variable=auto_var, command=toggle_auto)
    menu.add_separator()
    menu.add_command(label="關閉", command=quit_app)

    def on_menu(_e):
        x, y = cursor()
        menu.tk_popup(x, y)
        menu.grab_release()

    root.bind("<ButtonPress-1>", on_press)
    root.bind("<B1-Motion>", on_motion)
    root.bind("<ButtonRelease-1>", on_release)
    root.bind("<Double-Button-1>", on_double)
    root.bind("<ButtonPress-3>", on_menu)
    root.protocol("WM_DELETE_WINDOW", quit_app)

    def tick():
        now = time.perf_counter()
        dt = min(max(now - state["last"], 1 / 240), 1 / 15)
        state["last"] = now
        try:
            pet.cursor_pos = cursor()
            pet.step(dt)
            img, x, y = pet.frame()
            pet_win.push(img, x, y, rig.s)
            update_bubble()
            state["garden_t"] += dt
            if state["garden_t"] > 0.15:
                state["garden_t"] = 0.0
                garden.update(pet.t)
            state["home_t"] += dt
            if state["home_t"] > 0.12:
                state["home_t"] = 0.0
                render_home()
            state["topmost_t"] += dt
            if state["topmost_t"] > 2.0:
                state["topmost_t"] = 0.0
                pet_win.raise_top()
                if bub["shown"]:
                    bubble.raise_top()
        except Exception:
            import traceback

            traceback.print_exc()
        spent = (time.perf_counter() - now) * 1000
        root.after(max(1, int(33 - spent)), tick)

    root.after(10, tick)
    if "--home" in sys.argv:
        root.after(600, open_home)
    root.mainloop()


# ------------------------------------------------------------------ headless demo
def run_demo(out_path: str):
    rig = Rig(SCALE, build_pixel_sprites())
    WA = (0, 0, 900, 460)
    FAKE_WIN = (470, 250, 760, 460)  # 示範用的假視窗
    pet = Pet(rig, lambda _p: WA)
    pet.auto = False
    pet.P = [200.0, 150.0]
    pet.care = Care(None)
    pet.windows_fn = lambda: [(1, FAKE_WIN)]
    pet.win_rect_fn = lambda _h: FAKE_WIN
    flowers = []  # [x, floor, planted_t]；示範時生長加速 25 倍
    pet.on_plant = lambda x, f: flowers.append([x, f, pet.t])
    script = [
        ("look-at-mouse", lambda: pet.act_idle(2.4)),
        ("walk", lambda: pet.act_walk(1, 1.2 * pet.U, events=False)),
        ("plant", lambda: pet.act_plant()),
        ("eat", lambda: pet.act_eat()),
        ("bath", lambda: pet.act_bath()),
        ("sleep", lambda: pet.act_sleep(2.5)),
        ("trip", lambda: pet.act_trip()),
        ("climb", lambda: pet.act_climb()),
        ("on-window", lambda: pet.act_walk(1, 0.6 * pet.U, events=False)),
        ("jump_down", lambda: pet.act_jump_down(1)),
        ("frontflip", lambda: pet.act_frontflip()),
    ]
    frames = []
    stamps = []
    dt = 1 / 30
    bg = Image.new("RGBA", (WA[2], WA[3] + 20), (206, 214, 232, 255))
    dbg = ImageDraw.Draw(bg)
    dbg.rectangle((0, WA[3], WA[2], WA[3] + 20), fill=(120, 128, 150, 255))
    dbg.rectangle(FAKE_WIN, fill=(240, 240, 246, 255), outline=(90, 90, 110, 255))
    dbg.rectangle((FAKE_WIN[0], FAKE_WIN[1], FAKE_WIN[2], FAKE_WIN[1] + 18), fill=(60, 64, 90, 255))

    def snap(label, i):
        img, x, y = pet.frame()
        img = img.resize((img.width * rig.s, img.height * rig.s), Image.NEAREST)
        if i % 2 == 0:
            f = bg.copy()
            for fx, ff, ft in flowers:
                st = flower_stage((pet.t - ft) * 25)
                fl = draw_moonflower(st, int(round(math.sin(pet.t * 1.3 + fx) * 1.2)), 1.0 if st == 4 else 0.0)
                fl = fl.resize((FLOWER_W * rig.s, FLOWER_H * rig.s), Image.NEAREST)
                f.alpha_composite(fl, (int(fx - fl.width / 2), int(ff - fl.height)))
            f.alpha_composite(img, (x, y)) if 0 <= x and 0 <= y else f.paste(img, (x, y), img)
            if pet.speech and pet.t < pet.speech[1]:
                bb = render_bubble(pet.speech[0])
                bb = bb.resize((bb.width * rig.s, bb.height * rig.s), Image.NEAREST)
                f.paste(bb, (int(pet.P[0] - bb.width / 2), int(pet.P[1] + pet.extent()[0] - bb.height)), bb)
            if pet.cursor_pos:
                cx, cy = map(int, pet.cursor_pos)
                ImageDraw.Draw(f).polygon([(cx, cy), (cx, cy + 16), (cx + 11, cy + 11)], fill=(20, 20, 20, 255))
            ImageDraw.Draw(f).text((10, 8), label, fill=(40, 40, 60, 255))
            frames.append(f.convert("RGB").resize((630, 336), Image.NEAREST))
            stamps.append(label)

    i = 0
    # 入場落下
    while pet.action is not None and i < 200:
        pet.step(dt)
        snap("drop-in", i)
        i += 1
    for label, fn in script:
        pet.run(fn())
        n = 0
        while pet.action is not None and n < 900:
            if label == "look-at-mouse":
                ang = n / 72 * 2 * math.pi
                pet.cursor_pos = (pet.P[0] + math.cos(ang) * 260, pet.P[1] - 40 + math.sin(ang) * 120)
            else:
                pet.cursor_pos = None
            pet.step(dt)
            snap(label, i)
            i += 1
            n += 1
            if pet.action is None:
                break
    # 拖曳甩動後放開
    pet.run(pet.act_idle(0.2))
    for _ in range(8):
        pet.step(dt)
    gx, gy = pet.P[0], pet.P[1] - rig.dh * 0.7
    pet.grab(gx, gy)
    for n in range(75):
        mx = gx + math.sin(n / 30 * 2 * math.pi * 1.2) * 160 + n * 3
        my = gy - min(n, 30) * 6
        pet.drag_to(mx, my)
        pet.step(dt)
        snap("drag", i)
        i += 1
    pet.release()
    n = 0
    while pet.action is not None and n < 300:
        pet.step(dt)
        snap("throw", i)
        i += 1
        n += 1
    frames[0].save(out_path, save_all=True, append_images=frames[1:], duration=66, loop=0)
    # 縮圖總覽
    pick = np.linspace(0, len(frames) - 1, 40).astype(int)
    sheet = Image.new("RGB", (250 * 8, 145 * 5))
    for j, k in enumerate(pick):
        sheet.paste(frames[k].resize((250, 145)), ((j % 8) * 250, (j // 8) * 145))
    sheet.save(str(Path(out_path).with_suffix(".png")))
    print(f"frames={len(frames)} -> {out_path}")


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "--demo":
        run_demo(sys.argv[2])
    elif len(sys.argv) >= 2 and sys.argv[1] == "--rebuild-sprites":
        build_pixel_sprites(force=True)
        print(f"已重新產生點陣圖：{PIXEL_DIR}")
    else:
        run_app()
