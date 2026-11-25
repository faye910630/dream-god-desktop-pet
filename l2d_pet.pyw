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

FROZEN = getattr(sys, "frozen", False)  # PyInstaller 打包後的 exe
# 打包後：素材（點陣圖、字型、圖示）在 exe 內部（_MEIPASS）；Unity 小遊戲放在 exe 旁邊
ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)) if FROZEN else Path(__file__).resolve().parent
APP_DIR = Path(sys.executable).resolve().parent if FROZEN else ROOT
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
BUBBLE_SCALE = 1  # 說話泡泡的字用 11px 點陣字原生大小

SHOULDER_ROW = 30  # 側面圖（64 格）肩膀所在列
NECK_ROW = 28  # 正面轉頭時，頭／身體的分界列
ARM_SWING = 40.0  # 走路時手臂擺動角度
WALK_SPEED = 0.26  # 走路速度（角色高度／秒）
WALK_STEP_HZ = 1.3  # 每秒步伐循環數
WALK_STRIDE = 4.0  # 跨步（點陣格）
TRIP_CHANCE = 0.08  # 每次走路跌倒的機率
FOLLOW_START = 1.1  # 滑鼠離她超過幾個角色寬就跟過去（角色高度單位）
FOLLOW_STOP = 0.45  # 走到離滑鼠這麼近就停
FOLLOW_IDLE_S = 2.5  # 滑鼠停止移動多久後就不跟了
FOLLOW_SPEED = 0.4  # 跟著滑鼠走時的速度（比散步快一點）
FOLLOW_STEP_HZ = 2.0
CLIMB_SPEED = 0.45  # 爬視窗速度（角色高度／秒）
ARM_PATTERN = [  # 她不會露出手：袖子一路蓋到底，袖口是深色荷葉邊
    "..ooo..",
    ".o###o.",
    ".o###o.",
    ".o####o",
    "o#####o",
    "o#####o",
    "o#####o",
    "o#####o",
    "o#####o",
    "oFFFFFo",
    "oF.F.Fo",
    ".o.o.o.",
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
    "W": (252, 252, 248, 255),  # 花瓣（近純白）
    "w": (236, 238, 228, 255),  # 花瓣外緣微陰影
    "y": (210, 224, 150, 255),  # 五道星紋（淡綠奶油）
    "c": (228, 232, 160, 255),  # 花心
    "D": (92, 70, 58, 255),  # 土
    "d": (122, 96, 76, 255),  # 土亮部
}
# 心形葉（月光花葉）
_LEAF = [
    ".LL.LL.",
    "LGgLGGL",
    "LGgGGGL",
    "LGGgGGL",
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
    """正面月光花（Ipomoea alba）：近圓白瓣＋由花心放射到外緣的五道淡綠星紋。"""
    R = 6.6 * open_frac
    mask = np.zeros(arr.shape[:2], bool)
    # 五道星紋：一尖朝上
    rays = [math.radians(-90 + 72 * k) for k in range(5)]
    for y in range(arr.shape[0]):
        for x in range(arr.shape[1]):
            dx, dy = x - cx, y - cy
            r = math.hypot(dx, dy)
            th = math.atan2(dy, dx)
            # 幾乎正圓，外緣只做很淺的五瓣起伏
            edge = R * (0.97 + 0.03 * math.cos(5 * (th + math.pi / 2)))
            if r > edge:
                continue
            mask[y, x] = True
            # 白瓣：外緣略暗一點
            col = _C["w"] if r > R * 0.78 else _C["W"]
            # 星紋：靠射線越近越綠，內寬外尖
            rib_w = 0.35 + 0.55 * (1.0 - r / max(R, 0.01))
            on_rib = False
            for a in rays:
                dth = (th - a + math.pi) % (2 * math.pi) - math.pi
                if abs(dth) * max(r, 0.4) < rib_w and r > 0.4:
                    on_rib = True
                    break
            if on_rib:
                col = _C["y"]
            if r < R * 0.22:
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


def draw_bouquet() -> Image.Image:
    """月光花花束：真實月光花（圓白瓣＋五道淡綠星紋）＋心形葉＋黑包裝／金星網紗。"""
    W, H = 25, 28
    arr = np.zeros((H, W, 4), np.uint8)
    ink = OUTLINE
    black = (28, 26, 34, 255)
    black_l = (48, 44, 56, 255)
    gold = (232, 210, 120, 255)
    # 莖
    for x, y0 in ((9, 13), (12, 11), (15, 13), (11, 14), (14, 14)):
        for y in range(y0, 19):
            if 0 <= x < W:
                arr[y, x] = _C["S"]
    # 心形葉（塞在花叢間）
    _stamp(arr, _LEAF, 2, 10)
    _stamp(arr, _LEAF, 16, 11, flip=True)
    _stamp(arr, _LEAF, 4, 14)
    # 月光花（正面，星紋朝上）
    _bloom(arr, 9.0, 9.0, 0.95)
    _bloom(arr, 16.0, 8.0, 1.05)
    _bloom(arr, 12.5, 5.5, 1.0)
    _bloom(arr, 7.0, 12.5, 0.75)
    _bloom(arr, 17.5, 12.0, 0.75)
    # 黑網紗＋金色小星
    for y in range(2, 15):
        for x in range(3, 22):
            if arr[y, x, 3] == 0:
                continue
            if (x + y * 3) % 8 == 0:
                arr[y, x] = gold
            elif (x * 2 + y) % 6 == 0:
                r, g, b, a = (int(v) for v in arr[y, x])
                arr[y, x] = (max(24, r * 3 // 4), max(24, g * 3 // 4), max(30, b * 3 // 4), a)
    # 黑色錐形包裝
    wrap = [
        "......ooooo......",
        ".....o#####o.....",
        "....o#######o....",
        "...o#########o...",
        "...o#########o...",
        "....o#######o....",
        ".....ooooooo.....",
    ]
    for j, row in enumerate(wrap):
        for i, ch in enumerate(row):
            if ch == ".":
                continue
            x, y = 3 + i, 17 + j
            if 0 <= x < W and 0 <= y < H:
                arr[y, x] = ink if ch == "o" else (black_l if (i + j) % 3 == 0 else black)
    return Image.fromarray(arr)


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


_CANDY = dict(_PC, W=(255, 255, 255, 255), w=(232, 234, 246, 255), S=(255, 252, 226, 255),
              o=(150, 148, 186, 255), g=(196, 222, 160, 255), c=(222, 228, 130, 255))
STAR_CANDY = [  # 白色星星糖果（中間是一朵月光花）：一口比一口小
    _pix([
        "....o....",
        "...oWo...",
        "...ogo...",
        "ooooWoooo",
        "oWWgcgWWo",
        ".oWWgWwo.",
        "..ogWgo..",
        ".oWwowWo.",
        ".oWo.owo.",
        ".oo...oo.",
    ], _CANDY),
    _pix([
        "...o...",
        "..ogo..",
        "ooWgWoo",
        "oWgcgwo",
        ".oWgwo.",
        "oWwowWo",
        "oo...oo",
    ], _CANDY),
    _pix([
        "..o..",
        ".ogo.",
        "ogcgo",
        ".owo.",
        "o...o",
    ], _CANDY),
]
HOLD_PATTERN = [  # 用大袖子捧著糖果（手藏在袖子裡，不露出來）
    "o###o...o###o",
    "o###o...o###o",
    "o###o...o###o",
    "oFFFo...oFFFo",
    ".o.o.....o.o.",
]
MOUTH_ROW = 24  # 正面圖（64 格）嘴巴所在列


BED_LIFT = 10  # 床墊離地高度（點陣格）；躺著時床墊以下的身體不畫（像蓋在被子裡）


def make_moonflower_bed(glow=0.0):
    """月光花小床：一張真正的小床（床架、床頭、床尾、床墊、枕頭、被子），用月光花與藤蔓裝飾。
    側面視角，頭在左邊。回傳 (後層：床架／床墊／枕頭／床頭, 前層：被子＋床尾，會蓋住她的身體)。
    兩層同尺寸、底部對齊地面。"""
    W, H = 78, 30
    floor = H - 1
    mat_top = floor - BED_LIFT  # 床墊上緣（她躺在這裡）
    frame = (222, 216, 238, 255)
    frame_d = (176, 170, 206, 255)
    line = (98, 94, 128, 255)
    sheet = (248, 248, 242, 255)
    sheet_d = (222, 224, 228, 255)
    leaf = (98, 150, 84, 255)
    leaf_d = (36, 62, 42, 255)
    vine = (84, 122, 66, 255)

    back = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    front = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    db, df_ = ImageDraw.Draw(back), ImageDraw.Draw(front)

    # 床腳與床架側板
    for x0 in (3, W - 7):
        db.rectangle((x0, floor - 3, x0 + 2, floor), fill=frame_d, outline=line)
    db.rectangle((2, mat_top + 3, W - 3, floor - 3), fill=frame, outline=line)
    db.line((3, mat_top + 5, W - 4, mat_top + 5), fill=frame_d)
    # 床墊與床單
    db.rectangle((5, mat_top - 1, W - 6, mat_top + 3), fill=sheet, outline=line)
    db.line((6, mat_top + 2, W - 7, mat_top + 2), fill=sheet_d)
    # 床頭（左，高）：圓頂
    db.rectangle((1, 6, 6, floor - 3), fill=frame, outline=line)
    db.ellipse((0, 2, 8, 10), fill=frame, outline=line)
    db.line((3, 9, 3, floor - 4), fill=frame_d)
    # 枕頭（前層、矮矮的：她的頭枕在上面）
    df_.rounded_rectangle((5, mat_top - 4, 24, mat_top + 1), radius=2, fill=sheet, outline=line)
    df_.line((7, mat_top - 1, 22, mat_top - 1), fill=sheet_d)
    # 床尾（右，矮）—畫在前層，蓋住她的腳尖
    df_.rectangle((W - 6, mat_top - 6, W - 1, floor - 3), fill=frame, outline=line)
    df_.ellipse((W - 8, mat_top - 10, W + 1, mat_top - 2), fill=frame, outline=line)
    df_.line((W - 3, mat_top - 4, W - 3, floor - 4), fill=frame_d)
    # 被子改由 Pet.draw_quilt 依她的身體輪廓即時生成（保證蓋好不露出來）

    # 藤蔓與心形葉：沿著床頭與床架
    def put(img, x, y, c):
        if 0 <= x < W and 0 <= y < H:
            img.putpixel((x, y), c)

    for y in range(12, floor - 3, 2):
        put(back, 6 if (y // 2) % 2 else 5, y, vine)
    for i, x in enumerate(range(8, W - 8, 7)):
        y = mat_top + 6 + (1 if i % 2 else 0)
        put(back, x, y, vine)
        put(back, x + 1, y + (1 if i % 2 else -1), vine)
        if i % 2 == 0:
            for dx, dy in ((0, 0), (1, 0), (0, 1), (1, 1), (2, 0)):
                put(back, x + 2 + dx, y + 1 + dy, leaf)
            put(back, x + 3, y + 3, leaf_d)
    for x, y in ((7, 15), (7, 21)):  # 床頭上的心形葉
        for dx, dy in ((0, 0), (2, 0), (0, 1), (1, 1), (2, 1), (1, 2)):
            put(back, x + dx, y + dy, leaf)

    # 月光花：床頭頂端一朵大的，床架上幾朵小的（夜裡會發光）
    arr_b = np.array(back)
    if glow > 0:
        halo = np.zeros_like(arr_b)
        for cx, cy, rr in ((5, 6, 7.5), (W - 4, mat_top - 6, 5.5)):
            yy, xx = np.mgrid[0:H, 0:W]
            r = np.hypot(xx - cx, yy - cy)
            halo[(r <= rr) & (r > rr - 2.2)] = (236, 248, 255, int(80 * glow))
        e = arr_b[..., 3] == 0
        arr_b[e] = halo[e]
    _bloom(arr_b, 5, 6, 0.72)
    for x, y in ((24, mat_top + 6), (44, mat_top + 7), (62, mat_top + 6)):
        _bloom(arr_b, x, y, 0.4)
    arr_f = np.array(front)
    _bloom(arr_f, W - 4, mat_top - 6, 0.5)
    return Image.fromarray(arr_b), Image.fromarray(arr_f)


SLEEP_MIN_S = 90.0  # 至少睡這麼久（體力回滿也不會馬上起來）
SLEEP_MAX_S = 180.0


PILLOW = _pix([
    "..oooooooooooooooooo..",
    ".occccccccccccccccccco.",
    "occccccccccccccccccccco",
    "oCcccccccccccccccccCCCo",
    ".oCCCCCCCCCCCCCCCCCCCo.",
    "..ooooooooooooooooooo..",
], _PC)

FOAM = _pix([
    "......oWo.......",
    ".....oWsWo......",
    "......oWo.......",
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
# 個性：不善言辭、無口、面癱。話很少、很短，大多是「……」；表情幾乎不變，
# 情緒只會從小動作（歪頭、盯著看、默默跟過去）透出來。
PET_NAME = "朵莉姆"
PERSONA = "朵莉姆：花仙之中、夢境裡的神明；不善言辭、無口、面癱，背上有白色半透明的翅膀"
CHATTER_CHANCE = 0.1  # 發呆時自言自語的機率（無口，所以很低）
LINES = {
    "idle": ["……", "…", "……嗯。", "（發呆）", "……風。", "……月亮。", "……花。", "（盯——）"],
    "night": ["……夜晚。", "……花，在發光。", "……該睡了。"],
    "click": ["……？", "……", "……幹嘛。", "……嗯。", "（盯——）", "……不要戳。"],
    "eat": ["……好吃。", "……嗯。", "……還要。"],
    "hungry": ["……餓。", "……星星糖。"],
    "dirty": ["……想洗澡。"],
    "sleepy": ["……睏。"],
    "trip": ["……", "……痛。", "……沒事。"],
    "chat": ["……", "……嗯。", "……這樣啊。", "……知道了。", "（點頭）", "……？", "……朵莉姆在聽。"],
    "follow": ["……", "（跟——）", "……去哪。"],
    "wish": ["……", "……願。", "…………", "……星星。"],
}

CHAT_RULES = [
    (("吃", "餓", "糖", "點心", "飯"), "eat", "……開動。"),
    (("洗", "澡", "髒"), "bath", "……洗。"),
    (("醒", "起床"), "wake", "……醒了。"),
    (("睡", "累", "晚安", "休息"), "sleep", "……晚安。"),
    (("爬", "窗"), "climb", "……爬。"),
    (("下來",), "jump_down", "……好。"),
    (("跳",), "bounce", "……跳。"),
    (("翻",), "frontflip", "……翻。"),
    (("轉",), "spin", "……轉。"),
    (("花", "種"), "plant", "……種花。"),
    (("吊",), "hang", "……倒過來。"),
    (("跳舞", "舞"), "dance", "……跳。"),
    (("彈", "琴", "音樂", "唱"), "harp", "……彈一首。"),
    (("花束", "布偶", "玩偶", "娃娃", "花"), "plush", "……抱抱。"),
    (("星星", "接"), "stars", "……接星星。"),
    (("願", "許願", "流星", "祈禱"), "wish", "……願。"),
    (("換裝", "衣服", "穿"), "outfit", "……換衣服。"),
    (("遊戲", "雲", "玩"), "game", "……上去。"),
    (("走", "散步"), "walk", "……走。"),
    (("跌", "摔"), "trip", "……才不會。"),
    (("早安", "你好", "嗨", "哈囉", "hi", "hello"), None, "……你好。"),
    (("喜歡", "愛"), None, "…………我也是。"),
    (("名字", "你是誰", "叫什麼"), None, "……朵莉姆。夢的神明。"),
    (("朵莉姆",), None, "……嗯？叫我嗎。"),
    (("謝謝",), None, "……嗯。"),
    (("山谷", "家"), None, "……山谷。永遠的夜。"),
]


def respond(text: str):
    t = text.lower()
    for keys, act, reply in CHAT_RULES:
        if any(k in t for k in keys):
            return reply, act
    return random.choice(LINES["chat"]), None


DREAM_TALK = [
    "……我在夢裡種花。月光花，只在夜裡開。",
    "……雲的上面，有很亮的星星。",
    "……夢裡下雪的時候，四周很安靜。",
    "……有時候會夢到你。……只是有時候。",
    "……山谷一直是晚上。我喜歡。",
]


# ------------------------------------------------------------------ 照顧數值
CARE_KEYS = ("hunger", "clean", "mood", "energy")
CARE_NAMES = {"hunger": "飽食", "clean": "清潔", "mood": "心情", "energy": "體力"}
CARE_DECAY = {"hunger": 10.0, "clean": 6.0, "mood": 5.0, "energy": 8.0}  # 每小時下降
SLEEP_ENERGY_PER_S = 0.9  # 睡覺時每秒回復體力（睡久一點）


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


BUBBLE_FONT_PX = 14  # 桌面上的說話泡泡字體大小（至少 14px）


def render_bubble(text: str, size: int = BUBBLE_FONT_PX) -> Image.Image:
    """原生解析度的說話泡泡（白底、深色外框、下方小尾巴）。"""
    font = pixel_font(size)
    lines = _wrap(text, 10)
    tmp = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    tw = max(int(tmp.textlength(ln, font=font)) for ln in lines)
    lh = size + 2
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


# ------------------------------------------------------------------ 花仙的白色半透明翅膀
WING_ROOT_ROW = 33  # 正面／背面：翅膀根部在 64 格中的列（肩胛骨）
WING_ALPHA = 145


def make_fairy_wing():
    """單邊翅膀（往右長）：上大下小兩片、白色半透明、淡紫邊與翅脈。回傳 (RGBA 陣列, 根部所在列)。"""
    W, H, root = 32, 36, 22
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float64)
    ly = yy - root

    def ell(cx, cy, rx, ry, ang):
        t = math.radians(ang)
        c, sn = math.cos(t), math.sin(t)
        dx, dy = xx - cx, ly - cy
        u = (dx * c + dy * sn) / rx
        v = (-dx * sn + dy * c) / ry
        return u * u + v * v <= 1.0

    upper = ell(16, -9, 15, 8.5, -28)
    lower = ell(11, 6, 9, 5.5, 25)
    stem = (xx < 4) & (np.abs(ly) < 2.5)
    m = upper | lower | stem
    inner = m.copy()
    inner[1:] &= m[:-1]
    inner[:-1] &= m[1:]
    inner[:, 1:] &= m[:, :-1]
    inner[:, :-1] &= m[:, 1:]
    edge = m & ~inner
    a = np.zeros((H, W, 4), np.uint8)
    a[m] = (246, 248, 255, WING_ALPHA)
    # 翅脈：從根部放射出去
    for tx, ty in ((28, -16), (22, -3), (17, 10), (10, -16), (6, 9)):
        n = int(max(abs(tx), abs(ty))) * 2
        for i in range(n + 1):
            x = int(round(1 + (tx - 1) * i / n))
            y = int(round(root + ty * i / n))
            if 0 <= x < W and 0 <= y < H and m[y, x]:
                a[y, x] = (232, 236, 255, 185)
    a[edge] = (188, 192, 232, 225)
    # 上翅外緣幾點亮光
    for x, y in ((24, root - 15), (27, root - 11), (14, root + 9)):
        if m[y, x]:
            a[y, x] = (255, 255, 255, 235)
    return a, root


# ------------------------------------------------------------------ 小遊戲：雲端之夢
def shrink_pixel_sprite(img: Image.Image) -> Image.Image:
    """64 格點陣 → 32 格：每 2×2 取出現最多的顏色（平手取較深色），保持點陣清楚；外框重新描一圈。"""
    a = np.asarray(img.convert("RGBA"))
    h, w = a.shape[0] // 2, a.shape[1] // 2
    out = np.zeros((h, w, 4), np.uint8)
    for y in range(h):
        for x in range(w):
            blk = a[2 * y:2 * y + 2, 2 * x:2 * x + 2].reshape(4, 4)
            op = [tuple(c) for c in blk if c[3] > 0 and tuple(c[:3]) != OUTLINE[:3]]
            if len([c for c in blk if c[3] > 0]) < 2 or not op:
                continue
            best = max(set(op), key=lambda c: (op.count(c), -(c[0] * 0.299 + c[1] * 0.587 + c[2] * 0.114)))
            out[y, x] = best
    m = out[..., 3] > 0
    nb = np.zeros_like(m)
    nb[1:] |= m[:-1]
    nb[:-1] |= m[1:]
    nb[:, 1:] |= m[:, :-1]
    nb[:, :-1] |= m[:, 1:]
    out[nb & ~m] = OUTLINE
    return Image.fromarray(out)


def make_small_sprites(sprites64: dict):
    """小遊戲用的 32 格角色（正面／左／右）＋半尺寸翅膀；直接用目前（含換裝）的 64 格點陣縮小。"""
    out = {k: shrink_pixel_sprite(sprites64[k]) for k in ("front", "left", "right")}
    w, root = make_fairy_wing()
    wing = Image.fromarray(w).resize((w.shape[1] // 2, w.shape[0] // 2), Image.NEAREST)
    out["wing"] = (wing, root // 2)
    return out


class CloudGame:
    """一層一層往上跳：月光花山谷 → 薄霧 → 雲海 → 雲端之上的星空。"""

    W, H = 180, 270
    GRAV = 520.0
    JUMP = 255.0
    SPEED = 95.0
    GOAL = 2400  # 「雲端之上」的高度（遊戲內像素）
    TITLE = "雲端之夢"
    HELP = "← → / A D 或滑鼠左右移動・一層一層跳到雲端之上"
    SAVE_KEY = "best_cloud"
    BANDS = [  # (高度, 天空上緣色, 天空下緣色)
        (0, (6, 6, 12), (20, 16, 38)),
        (700, (18, 20, 44), (40, 46, 84)),
        (1500, (58, 66, 112), (140, 150, 196)),
        (2100, (20, 24, 60), (70, 76, 130)),
        (2600, (6, 8, 24), (22, 22, 58)),
    ]

    def __init__(self, sprites, best=0):
        self.spr = sprites
        self.best = best
        self.mouse = None
        self.reset()

    def reset(self):
        self.x, self.y = self.W / 2, 10.0
        self.vx, self.vy = 0.0, self.JUMP
        self.cam = 0.0
        self.top_gen = 10.0
        self.platforms = [dict(x=self.W / 2, y=8.0, w=self.W, kind="ground", vx=0.0, alive=True)]
        self.items = []
        self.fx = []
        self.height = 0.0
        self.stars = 0
        self.state = "play"
        self.just_over = False
        self.reached = False
        self.banner_t = 0.0
        self.face = 0
        self.t = 0.0
        self.squash = 0.0
        self.gen_until(self.H + 80)

    @property
    def meters(self):
        return int(self.height / 8)

    def gen_until(self, h):
        while self.top_gen < h:
            gap = 24 + min(20, self.top_gen / 160)
            self.top_gen += random.uniform(gap * 0.75, gap * 1.15)
            y = self.top_gen
            if y < 700:
                kind = "leaf"
            elif y < 1500:
                kind = "cloud"
            else:
                kind = random.choice(["cloud", "cloud", "bubble"])
            w = 22 if kind == "bubble" else random.randint(24, 38)
            vx = random.choice([0, 0, 0, 20, -20]) if (kind == "cloud" and y > 900) else 0
            self.platforms.append(dict(x=random.uniform(w / 2 + 2, self.W - w / 2 - 2), y=y, w=w, kind=kind,
                                       vx=float(vx), alive=True))
            if random.random() < 0.28:
                self.items.append(dict(x=random.uniform(10, self.W - 10), y=y + random.uniform(14, 30), got=False))

    def click(self):
        if self.state == "over":
            self.reset()

    def step(self, dt, dx):
        self.t += dt
        self.just_over = False
        self.banner_t = max(0.0, self.banner_t - dt)
        self.squash = max(0.0, self.squash - dt * 4)
        for f in self.fx:
            f[0] += f[2] * dt
            f[1] += f[3] * dt
            f[4] -= dt
        self.fx = [f for f in self.fx if f[4] > 0]
        if self.state != "play":
            return
        if dx:
            self.vx = dx * self.SPEED
        elif self.mouse is not None:
            ddx = self.mouse - self.x
            if abs(ddx) > self.W / 2:  # 從另一邊繞過去比較近
                ddx -= math.copysign(self.W, ddx)
            self.vx = max(-self.SPEED, min(self.SPEED, ddx * 5))
        else:
            self.vx *= 0.85
        self.face = (1 if self.vx > 0 else -1) if abs(self.vx) > 12 else 0
        self.x = (self.x + self.vx * dt) % self.W
        self.vy -= self.GRAV * dt
        y0 = self.y
        self.y += self.vy * dt
        for pl in self.platforms:
            if pl["vx"]:
                pl["x"] += pl["vx"] * dt
                if pl["x"] < pl["w"] / 2 or pl["x"] > self.W - pl["w"] / 2:
                    pl["vx"] = -pl["vx"]
        if self.vy < 0:
            for pl in self.platforms:
                if pl["alive"] and y0 >= pl["y"] >= self.y and abs(self.x - pl["x"]) <= pl["w"] / 2 + 4:
                    self.y = pl["y"]
                    self.vy = self.JUMP
                    self.squash = 1.0
                    if pl["kind"] == "bubble":
                        pl["alive"] = False
                        for _ in range(6):
                            a = random.uniform(0, math.tau)
                            self.fx.append([pl["x"], pl["y"], math.cos(a) * 40, math.sin(a) * 40, 0.4, "pop"])
                    break
        for it in self.items:
            if not it["got"] and abs(it["x"] - self.x) < 9 and -4 < it["y"] - self.y < 26:
                it["got"] = True
                self.stars += 1
                for _ in range(5):
                    a = random.uniform(0, math.tau)
                    self.fx.append([it["x"], it["y"], math.cos(a) * 30, math.sin(a) * 30, 0.5, "spark"])
        self.height = max(self.height, self.y)
        if not self.reached and self.y >= self.GOAL:
            self.reached = True
            self.banner_t = 3.0
        target = self.y - self.H * 0.45
        if target > self.cam:
            self.cam = target
        self.gen_until(self.cam + self.H + 80)
        self.platforms = [pl for pl in self.platforms if pl["y"] > self.cam - 30]
        self.items = [it for it in self.items if it["y"] > self.cam - 30 and not it["got"]]
        if self.y < self.cam - 30:
            self.state = "over"
            self.just_over = True
            self.best = max(self.best, self.meters)

    # ---------------------------------------------------------- 繪圖
    def _sky(self, h):
        b = self.BANDS
        for i in range(len(b) - 1):
            if h < b[i + 1][0]:
                t = (h - b[i][0]) / (b[i + 1][0] - b[i][0])
                return [tuple(int(b[i][k][c] + (b[i + 1][k][c] - b[i][k][c]) * t) for c in range(3)) for k in (1, 2)]
        return [b[-1][1], b[-1][2]]

    def sy(self, y):
        return int(round(self.H - (y - self.cam)))

    def render(self):
        W, H = self.W, self.H
        top_c, bot_c = self._sky(self.cam + H / 2)
        img = np.zeros((H, W, 4), np.uint8)
        img[..., :3] = _dither_gradient(H, W, top_c, bot_c, 6)
        img[..., 3] = 255
        # 星星（越高越多越亮，視差捲動）
        rng = np.random.default_rng(3)
        bright = min(1.0, 0.35 + self.cam / 2400)
        for i in range(90):
            x = int(rng.integers(0, W))
            y = int((rng.integers(0, H * 3) + self.cam * 0.3) % H)
            tw = 0.5 + 0.5 * math.sin(self.t * rng.uniform(1, 3) + i)
            if tw * bright > 0.3:
                v = int(120 + 135 * tw * bright)
                img[H - 1 - y, x, :3] = (v, v, min(255, v + 20))
        out = Image.fromarray(img)
        d = ImageDraw.Draw(out)
        # 山谷底部：黑色山與滿地月光花
        base = self.sy(0)
        if base > -40:
            xs = np.arange(W)
            ridge = base - 40 + 18 * np.abs(np.sin(xs / W * math.pi * 1.3 + 0.4)) + 4 * np.sin(xs * 0.4)
            for x in range(W):
                y0 = int(ridge[x])
                if y0 < H:
                    d.line((x, max(y0, 0), x, H), fill=(8, 8, 12, 255))
                    if 0 <= y0 < H:
                        out.putpixel((x, y0), (52, 50, 78, 255))
            frng = random.Random(5)
            for i in range(40):
                fx, fy = frng.randint(0, W - 1), base - frng.randint(0, 30)
                if 0 <= fy < H:
                    g = int(170 + 80 * (0.5 + 0.5 * math.sin(self.t * 1.5 + i)))
                    out.putpixel((fx, fy), (g, g, min(255, g + 10), 255))
        # 雲海（約 1500～1700）
        for k in range(14):
            cy = self.sy(1520 + (k % 3) * 40)
            cx = (k * 37 + self.t * (4 + k % 3)) % (W + 60) - 30
            if -30 < cy < H + 30:
                for dx, dy, r in ((0, 0, 14), (14, 3, 11), (-13, 4, 10), (5, -6, 9)):
                    d.ellipse((cx + dx - r, cy + dy - r, cx + dx + r, cy + dy + r), fill=(214, 220, 240, 255))
        # 雲端之上：大月亮
        if self.cam > 1900:
            my = int(40 + max(0, 2600 - self.cam) * 0.15)
            d.ellipse((W - 70, my - 22, W - 26, my + 22), fill=(230, 232, 216, 255))
            d.ellipse((W - 56, my - 10, W - 46, my), fill=(208, 210, 196, 255))
        # 平台
        for pl in self.platforms:
            if not pl["alive"]:
                continue
            y = self.sy(pl["y"])
            if y < -10 or y > H + 10:
                continue
            x0, x1 = int(pl["x"] - pl["w"] / 2), int(pl["x"] + pl["w"] / 2)
            k = pl["kind"]
            if k == "ground":
                d.rectangle((0, y, W, y + 3), fill=(30, 46, 40, 255))
            elif k == "leaf":  # 月光花的葉子
                d.ellipse((x0, y - 1, x1, y + 5), fill=(36, 62, 42, 255))
                d.ellipse((x0 + 1, y, x1 - 1, y + 4), fill=(98, 150, 84, 255))
                d.line((x0 + 3, y + 2, x1 - 3, y + 2), fill=(146, 192, 118, 255))
                d.point((pl["x"], y - 2), fill=(246, 246, 238, 255))
            elif k == "cloud":
                col = (240, 242, 252, 255) if not pl["vx"] else (214, 226, 250, 255)
                for i in range(x0, x1, 6):
                    d.ellipse((i - 1, y - 3, i + 7, y + 4), fill=col)
                d.rectangle((x0 + 2, y, x1 - 2, y + 4), fill=col)
                d.line((x0 + 3, y + 4, x1 - 3, y + 4), fill=(180, 186, 214, 255))
            else:  # 夢泡泡：踩一次就破
                d.ellipse((x0, y - 6, x1, y + 6), outline=(176, 214, 244, 255))
                d.point((x0 + 5, y - 3), fill=(255, 255, 255, 255))
        # 星星糖
        for it in self.items:
            y = self.sy(it["y"])
            if -8 < y < H + 8:
                c = STAR_CANDY[2]
                bob = int(round(math.sin(self.t * 3 + it["x"]) * 1.5))
                out.alpha_composite(c, (int(it["x"]) - 2, y - 2 + bob)) if 0 <= int(it["x"]) - 2 and 0 <= y - 2 + bob \
                    else out.paste(c, (int(it["x"]) - 2, y - 2 + bob), c)
        for f in self.fx:
            col = (255, 248, 206, 255) if f[5] == "spark" else (196, 226, 250, 255)
            y = self.sy(f[1])
            if 0 <= int(f[0]) < W and 0 <= y < H:
                out.putpixel((int(f[0]), y), col)
        # 她（32 格點陣＋白色半透明翅膀）
        key = "front" if self.face == 0 else ("right" if self.face > 0 else "left")
        body = self.spr[key]
        wing, wroot = self.spr["wing"]
        flap = 1 - 0.5 * (0.5 + 0.5 * math.sin(self.t * 30))
        ww = max(1, int(wing.width * flap))
        wimg = wing.resize((ww, wing.height), Image.NEAREST)
        sq = self.squash
        bw, bh = body.width, max(1, int(body.height * (1 - 0.18 * sq)))
        bimg = body.resize((int(bw * (1 + 0.12 * sq)), bh), Image.NEAREST)
        px = int(round(self.x)) - bimg.width // 2
        feet = self.sy(self.y)
        py = feet - bh + 1
        root_y = py + int(16 * (1 - 0.18 * sq))
        layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        if self.face == 0:
            layer.paste(wimg, (int(self.x) + 1, root_y - wroot), wimg)
            m = ImageOps.mirror(wimg)
            layer.paste(m, (int(self.x) - 1 - m.width, root_y - wroot), m)
        else:
            m = ImageOps.mirror(wimg) if self.face > 0 else wimg
            ox = int(self.x) - self.face * 2 - (m.width if self.face > 0 else 0)
            layer.paste(m, (ox, root_y - wroot), m)
        layer.paste(bimg, (px, py), bimg)
        for wrap in (0, -W, W):  # 從邊邊繞過去時兩邊都畫
            if wrap == 0 or (px < 0 and wrap == W) or (px + bimg.width > W and wrap == -W):
                out.alpha_composite(layer, (0, 0)) if wrap == 0 else out.paste(layer, (wrap, 0), layer)
        # HUD
        d = ImageDraw.Draw(out)
        d.fontmode = "1"
        font = pixel_font(11)
        d.rectangle((2, 2, 72, 30), fill=(8, 8, 16, 255), outline=(60, 56, 92, 255))
        d.text((5, 3), f"{self.meters} m", font=font, fill=(232, 228, 255, 255))
        d.text((5, 16), f"★{self.stars}  最佳{self.best}", font=font, fill=(206, 226, 168, 255))
        goal_m = self.GOAL // 8
        if not self.reached:
            frac = min(1.0, self.height / self.GOAL)
            d.rectangle((W - 7, 6, W - 4, H - 6), fill=(30, 28, 46, 255))
            d.rectangle((W - 7, int(H - 6 - (H - 12) * frac), W - 4, H - 6), fill=(214, 236, 255, 255))
        if self.banner_t > 0:
            d.rectangle((0, H // 2 - 14, W, H // 2 + 14), fill=(10, 10, 24, 255))
            d.text((W // 2 - 33, H // 2 - 6), "……雲端之上。", font=font, fill=(255, 248, 206, 255))
        if self.state == "over":
            d.rectangle((10, H // 2 - 34, W - 10, H // 2 + 34), fill=(8, 8, 16, 255), outline=(150, 148, 186, 255))
            d.text((22, H // 2 - 28), "……掉下去了。", font=font, fill=(232, 228, 255, 255))
            d.text((22, H // 2 - 12), f"高度 {self.meters} m（目標 {goal_m} m）", font=font, fill=(206, 226, 168, 255))
            d.text((22, H // 2 + 4), f"星星糖 {self.stars}  最佳 {self.best} m", font=font, fill=(206, 226, 168, 255))
            d.text((22, H // 2 + 18), "空白鍵／點一下：再玩", font=font, fill=(176, 214, 244, 255))
        return out



class StarCatchGame:
    """接星星：在永夜山谷左右移動接星星糖／流星；無生命值，漏接或碰到惡夢都不結束。"""

    W, H = 180, 270
    SPEED = 115.0
    TITLE = "接星星"
    HELP = "← → / A D 或滑鼠左右移動・接住星星（無生命，Esc 離開）"
    SAVE_KEY = "best_stars"

    def __init__(self, sprites, best=0):
        self.spr = sprites
        self.best = best
        self.mouse = None
        self.reset()

    @property
    def meters(self):  # 讓外面用同一個欄位讀分數
        return self.score

    def reset(self):
        self.floor = self.H - 22
        self.x = self.W / 2
        self.vx = 0.0
        self.face = 0
        self.objs = []
        self.fx = []
        self.score = 0
        self.t = 0.0
        self.spawn_t = 0.6
        self.state = "play"
        self.just_over = False
        self.reached = False
        self.squash = 0.0
        self.hurt = 0.0

    def click(self):
        pass

    def level(self):
        return min(1.0, self.t / 90.0)

    def step(self, dt, dx):
        self.t += dt
        self.just_over = False
        self.squash = max(0.0, self.squash - dt * 4)
        self.hurt = max(0.0, self.hurt - dt)
        for f in self.fx:
            f[0] += f[2] * dt
            f[1] += f[3] * dt
            f[3] += 60 * dt
            f[4] -= dt
        self.fx = [f for f in self.fx if f[4] > 0]
        if dx:
            self.vx = dx * self.SPEED
        elif self.mouse is not None:
            self.vx = max(-self.SPEED, min(self.SPEED, (self.mouse - self.x) * 6))
        else:
            self.vx *= 0.8
        self.face = (1 if self.vx > 0 else -1) if abs(self.vx) > 14 else 0
        self.x = min(max(self.x + self.vx * dt, 10), self.W - 10)
        lv = self.level()
        self.spawn_t -= dt
        if self.spawn_t <= 0:
            self.spawn_t = random.uniform(0.9, 1.3) * (1 - 0.6 * lv)
            r = random.random()
            kind = "gold" if r < 0.12 else ("nightmare" if r < 0.12 + 0.18 + 0.12 * lv else "star")
            sp = random.uniform(55, 75) + 90 * lv
            if kind == "gold":
                sp *= 1.5
            self.objs.append(dict(x=random.uniform(10, self.W - 10), y=-8.0, vy=sp, kind=kind,
                                  vx=random.uniform(-12, 12) if kind == "gold" else 0.0, ph=random.uniform(0, 6)))
        keep = []
        top = self.floor - 30
        for o in self.objs:
            o["y"] += o["vy"] * dt
            o["x"] = min(max(o["x"] + o["vx"] * dt, 6), self.W - 6)
            if top <= o["y"] <= self.floor and abs(o["x"] - self.x) < 13:
                if o["kind"] == "nightmare":
                    self.hurt = 0.35
                    self.burst(o["x"], o["y"], "dark")
                else:
                    self.score += 3 if o["kind"] == "gold" else 1
                    self.squash = 1.0
                    self.burst(o["x"], o["y"], "spark")
                    self.best = max(self.best, self.score)
                continue
            if o["y"] > self.floor + 4:
                continue  # 漏接：不扣生命
            keep.append(o)
        self.objs = keep

    def burst(self, x, y, kind):
        for _ in range(6):
            a = random.uniform(0, math.tau)
            self.fx.append([x, y, math.cos(a) * 35, math.sin(a) * 35 - 20, 0.5, kind])

    def render(self):
        W, H = self.W, self.H
        img = np.zeros((H, W, 4), np.uint8)
        img[..., :3] = _dither_gradient(H, W, (4, 4, 12), (24, 20, 46), 6)
        img[..., 3] = 255
        rng = np.random.default_rng(9)
        for i in range(60):
            x, y = int(rng.integers(0, W)), int(rng.integers(0, H - 40))
            tw = 0.5 + 0.5 * math.sin(self.t * rng.uniform(1, 3) + i)
            if tw > 0.35:
                v = int(140 + 110 * tw)
                img[y, x, :3] = (v, v, min(255, v + 20))
        out = Image.fromarray(img)
        d = ImageDraw.Draw(out)
        d.ellipse((96, 40, 126, 70), fill=(226, 228, 214, 255))
        d.ellipse((104, 48, 110, 54), fill=(204, 206, 194, 255))
        # 地面與月光花
        d.rectangle((0, self.floor, W, H), fill=(8, 8, 12, 255))
        d.line((0, self.floor, W, self.floor), fill=(40, 44, 60, 255))
        frng = random.Random(4)
        for i in range(26):
            fx, fy = frng.randint(0, W - 1), self.floor + frng.randint(3, 20)
            g = int(170 + 80 * (0.5 + 0.5 * math.sin(self.t * 1.5 + i)))
            for dx, dy in ((0, 0), (1, 0), (-1, 0), (0, 1), (0, -1)):
                if 0 <= fx + dx < W and fy + dy < H:
                    out.putpixel((fx + dx, fy + dy), (g, g, min(255, g + 10), 255) if (dx, dy) != (0, 0)
                                 else (214, 226, 150, 255))
        # 落下物
        for o in self.objs:
            x, y = int(o["x"]), int(o["y"])
            if o["kind"] == "star":
                c = STAR_CANDY[1]
                out.paste(c, (x - c.width // 2, y - c.height // 2), c)
            elif o["kind"] == "gold":
                for k in range(1, 6):  # 流星尾巴
                    tx, ty = int(x - o["vx"] * 0.02 * k), y - k * 3
                    if 0 <= tx < W and 0 <= ty < H:
                        out.putpixel((tx, ty), (255, 240, 170, 255))
                c = STAR_CANDY[0]
                tint = Image.new("RGBA", c.size, (255, 226, 120, 255))
                gold = Image.composite(Image.blend(c, tint, 0.45), c, c)
                out.paste(gold, (x - c.width // 2, y - c.height // 2), gold)
            else:  # 惡夢球：紫黑色、會扭動
                r = 5
                wob = int(round(math.sin(self.t * 8 + o["ph"])))
                d.ellipse((x - r + wob, y - r, x + r + wob, y + r), fill=(52, 24, 70, 255), outline=(120, 70, 150, 255))
                d.point((x - 2 + wob, y - 1), fill=(255, 120, 160, 255))
                d.point((x + 2 + wob, y - 1), fill=(255, 120, 160, 255))
        for f in self.fx:
            col = {"spark": (255, 248, 206, 255), "dark": (150, 90, 180, 255), "miss": (120, 120, 150, 255)}[f[5]]
            if 0 <= int(f[0]) < W and 0 <= int(f[1]) < H:
                out.putpixel((int(f[0]), int(f[1])), col)
        # 她
        key = "front" if self.face == 0 else ("right" if self.face > 0 else "left")
        body = self.spr[key]
        wing, wroot = self.spr["wing"]
        flap = 1 - 0.25 * (0.5 + 0.5 * math.sin(self.t * 6))
        wimg = wing.resize((max(1, int(wing.width * flap)), wing.height), Image.NEAREST)
        sq = self.squash
        bh = max(1, int(body.height * (1 - 0.15 * sq)))
        bimg = body.resize((int(body.width * (1 + 0.1 * sq)), bh), Image.NEAREST)
        px, py = int(round(self.x)) - bimg.width // 2, self.floor - bh + 1
        root_y = py + int(16 * (1 - 0.15 * sq))
        if self.face == 0:
            out.paste(wimg, (int(self.x) + 1, root_y - wroot), wimg)
            m = ImageOps.mirror(wimg)
            out.paste(m, (int(self.x) - 1 - m.width, root_y - wroot), m)
        else:
            m = ImageOps.mirror(wimg) if self.face > 0 else wimg
            out.paste(m, (int(self.x) - self.face * 2 - (m.width if self.face > 0 else 0), root_y - wroot), m)
        if self.hurt > 0 and int(self.hurt * 12) % 2:
            pass  # 碰到惡夢時閃一下（不扣命）
        else:
            out.paste(bimg, (px, py), bimg)
        # HUD（無生命值）
        d = ImageDraw.Draw(out)
        d.fontmode = "1"
        font = pixel_font(11)
        d.rectangle((2, 2, 78, 30), fill=(8, 8, 16, 255), outline=(60, 56, 92, 255))
        d.text((5, 3), f"★ {self.score}", font=font, fill=(255, 248, 206, 255))
        d.text((5, 16), f"最佳 {self.best}", font=font, fill=(206, 226, 168, 255))
        return out


# ------------------------------------------------------------------ 換裝
# 每套衣服：上衣／裙子／蝴蝶結（陰影色, 主色）、蕾絲領、裙襬蕾絲、襪子、鞋子、頭上小翅膀，加上專屬細節。
# 目前有：原本的哥德黑洋裝、白色洋裝、婚紗（半透明頭紗＋花冠）。
OUTFITS = {
    "哥德黑（原本）": None,
    "白色洋裝": dict(top=((176, 172, 198), (242, 240, 248)), skirt=((176, 172, 198), (242, 240, 248)),
                 accent=((150, 140, 196), (200, 192, 234)), neck=((150, 140, 196), (200, 192, 234)),
                 lace=(255, 255, 255), hem=(214, 208, 238), shoes=((120, 112, 160), (180, 172, 214))),
    "婚紗": dict(top=((200, 200, 214), (252, 252, 255)), skirt=((200, 200, 214), (252, 252, 255)),
               accent=((210, 210, 226), (255, 255, 255)), neck=((210, 210, 226), (255, 255, 255)),
               orn=((214, 214, 228), (255, 255, 255)), lace=(255, 255, 255), hem=(232, 236, 250),
               shoes=((200, 200, 214), (252, 252, 255)), extras=("veil", "crown")),
}
DEFAULT_OUTFIT = "哥德黑（原本）"
WAIST_ROW = 41


def _tone(L, shade, base):
    t = np.clip((L - 25) / 70.0, 0, 1)[..., None] ** 0.8
    return (np.array(shade) + (np.array(base) - np.array(shade)) * t).astype(np.uint8)


def dress_sprite(img: Image.Image, key: str, spec) -> Image.Image:
    """把一張 64 格點陣圖換成指定的衣服（保留原本的皺褶明暗）。"""
    if not spec:
        return img
    a = np.array(img.convert("RGBA"))
    H, W = a.shape[:2]
    alpha = a[..., 3] > 0
    L = a[..., :3].astype(np.float32) @ np.array([0.299, 0.587, 0.114], np.float32)
    outl = np.all(a[..., :3] == np.array(OUTLINE[:3], np.uint8), -1)
    yy, xx = np.mgrid[0:H, 0:W]
    cols = alpha.sum(0)
    cx = int(round((cols * np.arange(W)).sum() / max(cols.sum(), 1)))
    bot = int(np.nonzero(alpha.any(1))[0].max())
    dark = alpha & ~outl & (L < 100)
    light = alpha & ~outl & (L >= 150)
    cl_top = {"bottom": 6, "top": 34}.get(key, 25)
    orn = dark & (yy < 10) & (key not in ("bottom", "top"))
    bows = dark & ((yy < cl_top) | ((yy < 30) & (np.abs(xx - cx) > 10))) & ~orn & (key not in ("top", "bottom"))
    shoes = dark & (yy >= bot - 3)
    neck = dark & (yy >= 25) & (yy <= 31) & (np.abs(xx - cx) <= 4) & (key in ("front", "fl"))
    clothes = dark & (yy >= cl_top) & ~bows & ~shoes & ~neck
    waist = WAIST_ROW if key not in ("bottom",) else 0
    top_m = clothes & (yy < waist)
    skirt_m = clothes & (yy >= waist)
    lace = light & (yy >= 24) & (yy <= 31) & (np.abs(xx - cx) <= 9) & (key in ("front", "fl", "back", "bl"))
    socks = light & (yy >= 44) & (np.abs(xx - cx) <= 10)
    out = a.copy()
    out[top_m, :3] = _tone(L[top_m], *spec["top"])
    out[skirt_m, :3] = _tone(L[skirt_m], *spec["skirt"])
    if spec.get("accent"):
        out[bows, :3] = _tone(L[bows], *spec["accent"])
    if spec.get("neck"):
        out[neck, :3] = _tone(L[neck], *spec["neck"])
    if spec.get("orn"):
        out[orn, :3] = _tone(L[orn], *spec["orn"])
    if spec.get("shoes"):
        out[shoes, :3] = _tone(L[shoes], *spec["shoes"])
    if spec.get("lace"):
        out[lace, :3] = spec["lace"]
    if spec.get("socks"):
        out[socks, :3] = spec["socks"]
    if spec.get("pleats"):
        pm = skirt_m & ((xx - cx) % 4 == 0)
        out[pm, :3] = (out[pm, :3] * 0.78).astype(np.uint8)
    if spec.get("hem"):
        for x in range(W):
            r = np.nonzero(skirt_m[:, x])[0]
            if r.size:
                out[r[-1], x, :3] = spec["hem"]
                if x % 3 != 0 and r.size > 1:
                    out[r[-2], x, :3] = spec["hem"]
    ex = spec.get("extras", ())

    def put(x, y, c):
        if 0 <= x < W and 0 <= y < H:
            out[y, x] = c

    if "veil" in ex:  # 半透明頭紗：沿著頭髮兩側往下垂
        hair = light & (yy < 30)
        near = np.zeros_like(hair)
        for dy in range(-1, 4):
            for dx in range(-3, 4):
                near |= np.roll(np.roll(hair, dy, 0), dx, 1)
        veil = near & ~alpha & (yy >= 6) & (yy <= 46)
        if key in ("front", "fl", "back", "bl"):
            veil &= np.abs(xx - cx) >= 8
        out[veil] = (250, 250, 255, 120)
        # 頭紗垂到肩膀下面
        for x in range(W):
            if veil[:, x].any():
                last = int(np.nonzero(veil[:, x])[0].max())
                for y in range(last, min(last + 10, H)):
                    if not alpha[y, x]:
                        out[y, x] = (250, 250, 255, 100)
    if "crown" in ex and key not in ("bottom",):
        top_row = int(np.nonzero(alpha.any(1))[0].min())
        for k, dx in enumerate((-10, -5, 0, 5, 10) if key in ("front", "back", "top") else (-6, 0, 6)):
            x, y = cx + dx, top_row + 3 + (1 if k % 2 else 0)
            for ox, oy in ((0, 0), (1, 0), (-1, 0), (0, 1), (0, -1)):
                put(x + ox, y + oy, (255, 255, 255, 255) if (ox, oy) != (0, 0) else (214, 226, 150, 255))
            put(x + 2, y + 1, (98, 150, 84, 255))
    return Image.fromarray(out)


def dress_all(sprites: dict, name: str) -> dict:
    spec = OUTFITS.get(name)
    return {k: dress_sprite(v, k, spec) for k, v in sprites.items()}


def sleeve_colors(name: str):
    spec = OUTFITS.get(name)
    if not spec:
        return (70, 66, 76, 255), (96, 92, 106, 255)
    shade, base = spec["top"]
    mid = tuple(int(shade[i] + (base[i] - shade[i]) * 0.55) for i in range(3)) + (255,)
    frill = tuple(spec["lace"]) + (255,) if spec.get("lace") else tuple(int(c * 0.85) for c in base) + (255,)
    return mid, frill


# ------------------------------------------------------------------ 玩具與音符（點陣）
PLUSH = draw_bouquet()  # 月光花花束（抱／拖／放下用）

NOTE_COLORS = {"n": (236, 230, 255, 255), "o": (150, 140, 196, 255)}
PARTICLES["note"] = _pix([
    "..oooo",
    "..onno",
    "..on.o",
    "..on..",
    "oonn..",
    "onnn..",
    ".oo...",
], NOTE_COLORS)
PARTICLES["note2"] = _pix([
    "...oo.",
    "...ono",
    "...on.",
    "...on.",
    ".oonn.",
    "onnnn.",
    ".ooo..",
], NOTE_COLORS)

LYRE = _pix([  # 月光小豎琴（琴頂有一朵月光花）
    ".oo.........oo.",
    "oFFo.......oFFo",
    ".oFo..oWo..oFo.",
    ".oFoooWyWoooFo.",
    ".oFFFFFFFFFFFo.",
    "..oF.s.s.s.Fo..",
    "..oF.s.s.s.Fo..",
    "..oF.s.s.s.Fo..",
    "..oF.s.s.s.Fo..",
    "..oF.s.s.s.Fo..",
    "..oFFs.s.sFFo..",
    "...oFFFFFFFo...",
    "...offfffffo...",
    "....ooooooo....",
], {"o": OUTLINE, "F": (232, 210, 140, 255), "f": (196, 168, 96, 255), "s": (252, 252, 255, 255),
    "W": (250, 250, 255, 255), "y": (222, 228, 130, 255)})


# ------------------------------------------------------------------ 音樂（程式合成的原創曲子）
SAMPLE_RATE = 22050


def _freq(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def _synth_tone(m, dur, kind):
    n = int(SAMPLE_RATE * dur)
    t = np.arange(n) / SAMPLE_RATE
    f = _freq(m)
    if kind == "harp":  # 撥弦：泛音快速衰減
        w = np.sin(2 * np.pi * f * t) + 0.45 * np.sin(4 * np.pi * f * t) + 0.18 * np.sin(6 * np.pi * f * t)
        env = np.exp(-t * 3.0)
    elif kind == "box":  # 音樂盒：清脆的高泛音
        w = np.sin(2 * np.pi * f * t) + 0.35 * np.sin(2 * np.pi * f * 4 * t)
        env = np.exp(-t * 4.0)
    else:  # bass
        w = np.sin(2 * np.pi * f * t) + 0.2 * np.sin(4 * np.pi * f * t)
        env = np.exp(-t * 2.5)
    att = np.minimum(1.0, t / 0.006)
    return w * env * att


def render_tune(events, bpm, length_beats):
    """events: (拍, midi, 長度拍, 音色, 音量)。回傳 16-bit PCM bytes 與每個音的開始秒數。"""
    sec = 60.0 / bpm
    total = int(SAMPLE_RATE * (length_beats * sec + 1.5))
    buf = np.zeros(total)
    for beat, m, dur, kind, vol in events:
        st = int(SAMPLE_RATE * beat * sec)
        tone = _synth_tone(m, max(dur * sec, 0.6) + 0.8, kind) * vol
        end = min(total, st + tone.size)
        buf[st:end] += tone[:end - st]
    buf = buf / max(1e-6, np.abs(buf).max()) * 0.55
    return (buf * 32767).astype(np.int16).tobytes(), sorted({b * sec for b, *_ in events})


def harp_lullaby():
    """月光搖籃曲（豎琴，3/4 拍，84 BPM）。"""
    arps = {"D": (50, 57, 62, 66, 62, 57), "Bm": (47, 54, 59, 62, 59, 54),
            "G": (43, 50, 55, 59, 55, 50), "A": (45, 52, 57, 61, 57, 52)}
    bars = [("D", (69, 78, 81)), ("Bm", (71, 74, 78)), ("G", (67, 71, 74)), ("A", (76, 73, 69)),
            ("D", (78, 81, 86)), ("Bm", (86, 83, 78)), ("G", (79, 76, 74)), ("D", (74, None, None))]
    ev = []
    for i, (ch, mel) in enumerate(bars):
        b0 = i * 3
        for k, m in enumerate(arps[ch]):
            ev.append((b0 + k * 0.5, m, 0.5, "harp", 0.45))
        for k, m in enumerate(mel):
            if m:
                ev.append((b0 + k, m, 1 if k < 2 or mel[2] else 3, "harp", 0.8))
    return render_tune(ev, 84, len(bars) * 3)


def dance_tune():
    """夢之舞（音樂盒，4/4 拍，120 BPM），兩遍。"""
    mel = [(74, 78, 81, 78, 83, 81, 78, 74), (79, 83, 86, 83, 81, 79, 78, 76),
           (76, 81, 85, 81, 79, 78, 76, 73), (74, 78, 81, 86, 81, 78, 74, None)]
    bass = [(50, 57, 50, 57), (43, 50, 43, 50), (45, 52, 45, 52), (50, 57, 50, 50)]
    ev = []
    for rep_i in range(2):
        for i in range(4):
            b0 = (rep_i * 4 + i) * 4
            for k, m in enumerate(mel[i]):
                if m:
                    ev.append((b0 + k * 0.5, m, 0.5, "box", 0.7))
            for k, m in enumerate(bass[i]):
                ev.append((b0 + k, m, 1, "bass", 0.5))
    return render_tune(ev, 120, 32)


HARP_TUNE = harp_lullaby()  # 載入時合成一次（也拿到每個音的時間點，用來同步撥弦動畫）
DANCE_TUNE = dance_tune()


# ------------------------------------------------------------------ 玩具（可以拖、會彈、會滾）
class Toy:
    def __init__(self, kind, x, y):
        self.kind = kind  # 目前只有 "plush"（月光花花束）
        self.x, self.y = x, y  # 底部中央（螢幕座標）
        self.vx = self.vy = 0.0
        self.angle = 0.0
        self.held = False  # 被滑鼠拿著
        self.carried = False  # 被她抱著
        self.size = (PLUSH.width, PLUSH.height)

    def image(self):
        return PLUSH

    def grounded(self, floor):
        return self.y >= floor - 1 and abs(self.vy) < 1

    def step(self, dt, work, g):
        if self.held or self.carried:
            self.vx = self.vy = 0.0
            return
        l, t, r, b = work
        hw = self.size[0] * SCALE / 2
        self.vy += g * dt
        self.x += self.vx * dt
        self.y += self.vy * dt
        if self.x < l + hw:
            self.x, self.vx = l + hw, abs(self.vx) * 0.7
        elif self.x > r - hw:
            self.x, self.vx = r - hw, -abs(self.vx) * 0.7
        if self.y - self.size[1] * SCALE < t:
            self.y, self.vy = t + self.size[1] * SCALE, abs(self.vy) * 0.5
        if self.y >= b:
            self.y = b
            rest = 0.15
            self.vy = -self.vy * rest if self.vy > 90 else 0.0
            self.vx *= max(0.0, 1 - 6.0 * dt)
            if abs(self.vx) < 3:
                self.vx = 0.0


class Rig:
    """8 張 64×64 點陣視圖 + 類 Live2D 參數變形（以整數像素位移，維持點陣風格）。

    物理與參數以「螢幕像素」計算；繪製在原生點陣解析度進行，最後以最近鄰整數倍放大。
    """

    def __init__(self, scale: int, sprites: dict[str, Image.Image], sleeve=None):
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
        dress, frill = sleeve or ((70, 66, 76, 255), (96, 92, 106, 255))
        arm_cols = {"o": OUTLINE, "#": dress, "F": frill}
        self.hold_hands = _pix(HOLD_PATTERN, {"o": OUTLINE, "#": dress, "F": frill})
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
        self.wing, self.wing_root = make_fairy_wing()

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

    def _wing_patch(self, out, root, side, sx, over, alpha_mul=1.0, dy=0):
        """把翅膀以根部為軸、水平縮放 sx（拍動／透視）貼上。side=+1 往右、-1 往左；
        over=False 畫在身體後面，True 疊在身體前面（半透明混合）。"""
        wing = self.wing
        h, w = wing.shape[:2]
        n = max(1, int(round(w * sx)))
        cols = np.arange(n)
        src = np.clip((cols / max(sx, 1e-3)).astype(int), 0, w - 1)
        X = root[0] + side * cols
        Y0 = root[1] - self.wing_root + dy
        okx = (X >= 0) & (X < CANVAS)
        X, src = X[okx], src[okx]
        for r in range(h):
            Y = Y0 + r
            if not 0 <= Y < CANVAS:
                continue
            px = wing[r, src].astype(np.float32)
            a = px[:, 3] * alpha_mul / 255.0
            vis = a > 0
            if not vis.any():
                continue
            Xv, pv, av = X[vis], px[vis], a[vis]
            dst = out[Y, Xv].astype(np.float32)
            if over:
                body = dst[:, 3] > 0
                mix = dst.copy()
                mix[:, :3] = pv[:, :3] * av[:, None] + dst[:, :3] * (1 - av[:, None])
                mix[:, 3] = np.maximum(dst[:, 3], av * 255)
                res = np.where(body[:, None], mix, np.concatenate([pv[:, :3], (av * 255)[:, None]], 1))
            else:
                empty = dst[:, 3] == 0
                res = np.where(empty[:, None], np.concatenate([pv[:, :3], (av * 255)[:, None]], 1), dst)
            out[Y, Xv] = res.astype(np.uint8)

    def compose_wings(self, arr: np.ndarray, view, flap: float) -> np.ndarray:
        key, mir = view
        if key in ("top", "bottom"):
            return arr
        out = arr.copy()
        cx, cy = CANVAS // 2, PAD + WING_ROOT_ROW
        if key == "front":
            for side in (1, -1):
                self._wing_patch(out, (cx + side * 2, cy), side, flap, over=False)
        elif key == "back":
            for side in (1, -1):
                self._wing_patch(out, (cx + side * 2, cy), side, flap, over=True)
        elif key in ("fl", "bl"):
            # 斜側：面向的那一側翅膀比較窄（透視）
            facing = -1 if not mir else 1
            over = key == "bl"
            for side in (1, -1):
                k = 0.6 if side == facing else 1.0
                self._wing_patch(out, (cx + side * 2, cy), side, flap * k, over=over, alpha_mul=1.0 if k == 1 else 0.85)
        else:  # 側面：翅膀往背後長
            sh = self.legs[view][6]
            f = self.legs[view][5]
            root = (sh[0] - f * 3, sh[1] + 2)
            self._wing_patch(out, (root[0] - f, root[1] - 1), -f, flap * 0.6, over=False, alpha_mul=0.7)
            self._wing_patch(out, root, -f, flap * 0.75, over=False)
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
        if params.get("wing_flap") is not None:
            arr = self.compose_wings(arr, view, params["wing_flap"])
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
        self.follow_enabled = True
        self.toys: list = []  # Toy，由 App 管理
        self.on_sound = None  # callback(name or None)：播放／停止音樂
        self.music_on = False
        self.busy_look = False
        self.clip_y = None
        self.quilt_frac = 0.0
        self.flying = False  # 飛行中（倒吊前飛上去）：翅膀快速拍動
        self.in_air = False
        self.wing_phase = 0.0
        self.wing_amp = 0.12
        self.cursor_last = None
        self.cursor_moved_t = -99.0
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
        # 翅膀：平常輕輕拍、空中拍快、飛行時用力拍
        if self.flying:
            hz, amp = 7.0, 0.55
        elif self.in_air or self.dragging:
            hz, amp = 4.5, 0.4
        elif self.sleeping:
            hz, amp = 0.5, 0.05
        else:
            hz, amp = 1.1, 0.14
        self.wing_phase += dt * 2 * math.pi * hz
        self.wing_amp += (amp - self.wing_amp) * min(1.0, dt * 6)
        if self.cursor_pos is not None:
            if self.cursor_last is None or abs(self.cursor_pos[0] - self.cursor_last[0]) + abs(
                    self.cursor_pos[1] - self.cursor_last[1]) > 4:
                self.cursor_moved_t = self.t
            self.cursor_last = self.cursor_pos
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
            "wing_flap": (None if self.clip_y is not None  # 躺在床裡：翅膀收起來（不畫）
                          else 1.0 - self.wing_amp * (0.5 + 0.5 * math.sin(self.wing_phase))),
        }

    def facing(self):
        return 1 if self.view in (("right", False), ("left", True)) else -1

    def frame(self):
        W = self.rig.W
        ox, oy = self.P[0] - W / 2, self.P[1] - W / 2
        wx, wy = math.floor(ox), math.floor(oy)
        sxT, syT = self.total_scale()
        img = self.rig.render(self.view, self.params(), self.rot + self.view_rot, sxT, syT, (ox - wx, oy - wy))
        if self.clip_y is not None:  # 躺在床裡：床墊以下不畫
            cut = int(round((self.clip_y - self.P[1]) / self.rig.s + WIN_N / 2))
            if cut < WIN_N:
                a = np.array(img)
                a[max(cut, 0):, :, 3] = 0
                img = Image.fromarray(a)
            if "bed" in self.props and self.quilt_frac > 0:
                img = self.draw_quilt(img, cut)
        if self.props or self.particles:
            img = self.compose_extras(img)
        return img, wx, wy

    def draw_quilt(self, img, mat):
        """月光花被子：沿著她露出床墊的身體輪廓往上多蓋 2 格，從頸部蓋到床尾，只露出頭。"""
        s = self.rig.s
        half = WIN_N / 2
        a = np.array(img)
        alpha = a[..., 3] > 0
        bed_left = (self.bed_x - self.P[0]) / s + half - 39  # 床圖左緣（床寬 78）
        x0, x1 = int(round(bed_left + 38)), int(round(bed_left + 72))
        mat = min(max(mat, 1), WIN_N - 5)
        tops = {}
        for x in range(max(x0, 0), min(x1, WIN_N - 1) + 1):
            col = np.nonzero(alpha[:mat, x])[0]
            tops[x] = int(col[0]) if col.size else mat - 3
        xs = sorted(tops)
        if not xs:
            return img
        # 平滑：取附近最高點、再做移動平均，往上多蓋 2 格；quilt_frac 控制被子拉上來的程度
        hi = {x: min(tops[k] for k in xs if abs(k - x) <= 3) for x in xs}
        avg = {x: sum(hi[k] for k in xs if abs(k - x) <= 3) / sum(1 for k in xs if abs(k - x) <= 3) for x in xs}
        f = self.quilt_frac
        sm = {x: int(round(mat - (mat - (min(avg[x], hi[x]) - 2)) * f)) for x in xs}
        quilt, quilt_d, quilt_l = (196, 188, 228, 255), (164, 156, 204, 255), (222, 216, 246, 255)
        line = (98, 94, 128, 255)
        for i, x in enumerate(xs):
            top = max(sm[x], 0)
            a[top:mat + 4, x] = quilt
            a[top, x] = line
            a[mat + 4, x] = line
            if x % 2 == 0:
                a[mat + 2, x] = quilt_d
            if i < 3:  # 翻折的被緣
                a[top + 1:mat + 3, x] = quilt_l
        a[max(sm[xs[0]], 0):mat + 5, xs[0]] = line
        a[max(sm[xs[-1]], 0):mat + 5, xs[-1]] = line
        for k, x in enumerate(xs[6:-3:9]):  # 被子上的小月光花
            y = max(sm[x], 0) + 4 + (k % 2) * 2
            if y + 1 < mat + 3:
                for dx, dy in ((0, 0), (1, 0), (-1, 0), (0, 1), (0, -1)):
                    a[y + dy, x + dx] = (250, 250, 255, 255) if (dx, dy) != (0, 0) else (214, 226, 150, 255)
        return Image.fromarray(a)

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
        self.flying = False
        self.in_air = False
        self.busy_look = False
        self.clip_y = None
        if self.music_on and self.on_sound:
            self.on_sound(None)
        self.music_on = False
        for toy in self.toys:  # 被打斷時把抱著的玩具放下
            if toy.carried:
                toy.carried = False
                toy.x, toy.y = self.P[0] + 0.3 * self.U, self.work[3]
        self.quilt_frac = 0.0
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
        if self.follow_want():
            self.last_kind = "follow"
            return self._chain(self.act_follow())
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
            elif random.random() < CHATTER_CHANCE:
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
            choices.append(("dance", 0.5, lambda: self.act_dance()))
            choices.append(("harp", 0.4, lambda: self.act_harp()))
            if any(tt.kind == "plush" for tt in self.toys):
                choices.append(("plush", 1.0, lambda: self.act_hug_plush()))
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
        self.in_air = True
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
                self.in_air = False
                return vy, vx
            yield

    # ---------------------------------------------------------- actions
    def act_idle(self, dur, face=True):
        if face:
            yield from self.turn_to(0)
        for _ in self.over(dur):
            if self.follow_want():
                return
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
            self.flying = True
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
        self.flying = False
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
        ok = (self.look_enabled and not self.busy_look and self.cursor_pos is not None and not self.dragging
              and self.stride == 0
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
                self.say("……！", 1.0)
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

    def follow_want(self):
        """滑鼠最近有在動、而且離她夠遠 → 想跟過去。"""
        if not (self.follow_enabled and self.auto) or self.cursor_pos is None or self.dragging or self.sleeping:
            return False
        if self.t - self.cursor_moved_t > 1.2:
            return False
        l, t, r, b = self.work
        cx, cy = self.cursor_pos
        if not (l <= cx <= r and t - 50 <= cy <= b + 50):
            return False
        return abs(cx - self.P[0]) > FOLLOW_START * self.U

    def act_follow(self):
        """默默地左右走到滑鼠下面，停下來盯著看。"""
        U = self.U
        hw = self.rig.hw
        phase = 0.0
        direction = 0
        if random.random() < 0.15:
            self.say(random.choice(LINES["follow"]), 1.2)
        while self.cursor_pos is not None and self.follow_enabled:
            dx = self.cursor_pos[0] - self.P[0]
            if abs(dx) < FOLLOW_STOP * U or self.t - self.cursor_moved_t > FOLLOW_IDLE_S:
                break
            d = 1 if dx > 0 else -1
            if d != direction:
                self.stride = 0.0
                self.a["lean"] = 0.0
                yield from self.turn_to(90 if d > 0 else 270, 0.07)
                direction = d
            l, t, r, b = self.work
            nx = self.P[0] + FOLLOW_SPEED * U * self.dt * d
            if nx > r - hw or nx < l + hw:
                break
            self.P[0] = nx
            phase += self.dt * 2 * math.pi * FOLLOW_STEP_HZ
            self.gait = phase
            self.stride = WALK_STRIDE
            self.a["lean"] = d * 0.025 * U
            self.a["head"] = math.cos(phase * 2) * 0.01 * U
            self.ground(abs(math.cos(phase)) * 0.016 * U)
            yield
        self.stride = 0.0
        self.a["lean"] = self.a["head"] = 0.0
        yield from self.turn_to(0)
        yield from self.act_idle(0.6, face=False)

    def act_change(self):
        """換好衣服：轉一圈、冒星光。"""
        for _ in range(10):
            self.spawn("spark", self.P[0] + random.uniform(-0.35, 0.35) * self.U,
                       self.P[1] + random.uniform(-0.45, 0.35) * self.U, 0, -0.12 * self.U, 0, 1.0)
        yield from self.act_spin(1)
        self.say("……換好了。")
        yield from self.act_idle(0.8, face=False)

    def music(self, name):
        if self.on_sound:
            self.on_sound(name)
            self.music_on = name is not None

    def act_dance(self):
        """跳舞：跟著音樂盒的節拍（120 BPM）搖擺、側步、小跳、轉圈，最後擺姿勢。"""
        U = self.U
        yield from self.turn_to(0)
        self.say("……♪", 1.2)
        self.music("dance")
        beat = 0.5
        phrases = ["sway", "sway", "step", "hop", "spin", "sway", "step", "spin"]
        for ph in phrases:
            if ph == "spin":
                start = self.yaw
                d = random.choice([1, -1])
                for p in self.over(beat * 4):
                    self.set_yaw(start + d * 360 * ease(p))
                    self.a["flare"] = 0.16 * math.sin(math.pi * p)
                    self.ground(math.sin(math.pi * p) * 0.06 * U)
                    yield
                self.set_yaw(0)
                self.a["flare"] = 0.0
                continue
            for b in range(4):
                side = 1 if b % 2 == 0 else -1
                self.spawn("note" if b % 2 else "note2", self.P[0] + side * random.uniform(0.2, 0.4) * U,
                           self.P[1] - 0.45 * U, side * 0.1 * U, -0.35 * U, 0, 1.4)
                if ph == "step":
                    self.set_yaw(315 if side > 0 else 45)
                for p in self.over(beat):
                    w = math.sin(math.pi * p)
                    if ph == "sway":
                        self.a["lean"] = side * 0.04 * U * w
                        self.a["head"] = -side * 0.02 * U * w
                        self.sy = 1 - 0.05 * w
                        self.ground()
                    elif ph == "step":
                        self.P[0] += side * 0.25 * U * self.dt
                        self.ground(0.05 * U * w)
                    else:  # hop
                        self.a["flare"] = 0.12 * w
                        self.ground(0.14 * U * w)
                    yield
                self.sy = 1.0
            self.a["lean"] = self.a["head"] = self.a["flare"] = 0.0
            self.set_yaw(0)
        # 收尾的姿勢：蹲一下、跳起來
        yield from self.crouch(0.15, 0.2)
        v0 = math.sqrt(2 * self.G * 0.45 * U)
        impact, _ = yield from self.airborne(0, -v0)
        self.kick(impact)
        self.music(None)
        if self.care:
            self.care.add("mood", 6)
            self.care.add("energy", -3)
        self.say("……跳完了。")
        yield from self.settle(0.3)

    def act_harp(self):
        """抱著月光小豎琴，用袖子撥弦，彈一首搖籃曲。"""
        U = self.U
        s = self.rig.s
        yield from self.turn_to(0)
        self.busy_look = True
        self.head_view = None
        self.say("……彈一首。", 1.4)
        _, onsets = HARP_TUNE
        self.music("harp")
        t0 = self.t
        dur = onsets[-1] + 1.5 if onsets else 8.0
        k = 0
        pluck = 0.0
        while self.t - t0 < dur:
            el = self.t - t0
            while k < len(onsets) and onsets[k] <= el:
                k += 1
                pluck = 1.0
                if k % 2 == 0:
                    self.spawn("note" if k % 4 else "note2", self.P[0] + random.uniform(-0.3, 0.3) * U,
                               self.P[1] - 0.2 * U, random.uniform(-0.1, 0.1) * U, -0.3 * U, 0, 1.6)
            pluck = max(0.0, pluck - self.dt * 8)
            my = self.mouth_y()
            harp_bottom = my + (LYRE.height + 6) * s
            self.props["harp"] = (LYRE, self.P[0], harp_bottom, "front")
            off = int(round(pluck)) * (1 if k % 2 else -1)
            self.props["hands"] = (self.rig.hold_hands, self.P[0] + off * s, harp_bottom - 2 * s, "front")
            self.a["head"] = math.sin(el * 2 * math.pi * 84 / 60 / 3) * 0.012 * U
            self.ground()
            yield
        self.music(None)
        self.props.pop("harp", None)
        self.props.pop("hands", None)
        self.busy_look = False
        self.a["head"] = 0.0
        if self.care:
            self.care.add("mood", 6)
        self.say("……♪")
        yield from self.act_idle(0.8, face=False)

    def nearest_toy(self, kind):
        toys = [tt for tt in self.toys if tt.kind == kind and not tt.held and not tt.carried]
        return min(toys, key=lambda tt: abs(tt.x - self.P[0])) if toys else None

    def act_hug_plush(self):
        """走到月光花花束旁邊，撿起來抱一抱，再放下。"""
        U = self.U
        s = self.rig.s
        plush = self.nearest_toy("plush")
        if not plush:
            self.say("……花束呢？")
            return
        for _tries in range(4):
            plush = self.nearest_toy("plush")
            if not plush:
                return
            gap = abs(plush.x - self.P[0])
            if gap < 0.3 * U:
                break
            yield from self.act_walk(1 if plush.x > self.P[0] else -1, gap - 0.15 * U, face_front=False, events=False)
        plush = self.nearest_toy("plush")
        if not plush:
            return
        yield from self.turn_to(0)
        for p in self.over(0.25):  # 彎腰撿起來
            self.sy = 1 - 0.15 * ease(p)
            self.ground()
            yield
        plush.carried = True
        self.busy_look = True
        self.head_view = None
        for p in self.over(0.25):
            self.sy = 0.85 + 0.15 * ease(p)
            self.ground()
            yield
        self.sy = 1.0
        self.say("……好香。", 1.6)
        for p in self.over(3.0):  # 抱在懷裡左右搖
            sway = math.sin(p * 3 * 2 * math.pi)
            self.a["lean"] = sway * 0.02 * U
            self.a["head"] = sway * 0.015 * U
            cb = self.mouth_y() + (PLUSH.height + 4) * s
            self.props["plush"] = (PLUSH, self.P[0] + sway * s, cb, "front")
            if random.random() < 0.02:
                self.spawn("heart", self.P[0], self.P[1] - 0.45 * U, 0, -0.3 * U, 0, 1.0)
            self.ground()
            yield
        self.a["lean"] = self.a["head"] = 0.0
        self.props.pop("plush", None)
        plush.carried = False
        side = random.choice([1, -1])
        plush.x, plush.y, plush.vx, plush.vy = self.P[0] + side * 0.32 * U, self.work[3], 0.0, 0.0
        self.busy_look = False
        if self.care:
            self.care.add("mood", 5)
        yield from self.act_idle(0.8, face=False)

    def act_tilt(self):
        """面癱的反應：不笑不跳，只是歪一下頭、盯著看。"""
        yield from self.turn_to(0, 0.06)
        d = random.choice([1, -1])
        for p in self.over(0.25):
            self.a["head"] = d * 0.03 * self.U * ease(p)
            self.ground()
            yield
        for _ in self.over(0.9):
            self.ground()
            yield
        for p in self.over(0.25):
            self.a["head"] = d * 0.03 * self.U * (1 - ease(p))
            self.ground()
            yield

    def act_wish(self):
        """許願：抬頭看天，流星劃過，無口地許一個願。"""
        U = self.U
        yield from self.turn_to(0, 0.1)
        self.say(random.choice(LINES["wish"]), 2.2)
        # 慢慢抬頭（視線往上、頭微揚）
        for p in self.over(0.55):
            e = ease(p)
            self.a["head"] = -0.05 * U * e
            self.look[1] = -0.85 * e
            self.ground()
            yield
        # 流星從畫面上方斜劃而下
        sx = self.P[0] + random.uniform(-0.8, 0.4) * U
        sy = self.P[1] - 1.6 * U
        for p in self.over(1.1):
            e = ease(p)
            mx = sx + 1.4 * U * e
            my = sy + 1.1 * U * e
            self.spawn("spark", mx, my, 0.15 * U, 0.12 * U, 0, 0.45)
            if random.random() < 0.55:
                self.spawn("spark", mx - 0.08 * U, my - 0.05 * U, 0.05 * U, 0.08 * U, 0, 0.35)
            self.a["head"] = -0.05 * U
            self.look[1] = -0.85
            self.ground()
            yield
        # 收尾：心口一小下，心情上升
        self.spawn("heart", self.P[0], self.P[1] - 0.4 * U, 0, -0.25 * U, 0, 1.0)
        if self.care:
            self.care.add("mood", 6)
        for p in self.over(0.4):
            e = 1 - ease(p)
            self.a["head"] = -0.05 * U * e
            self.look[1] = -0.85 * e
            self.ground()
            yield
        self.a["head"] = 0.0
        self.look[1] = 0.0
        yield from self.act_idle(0.6, face=False)

    # ---------------------------------------------------------- 互動動作
    def mouth_y(self):
        """嘴巴的世界座標 y（正面、站直時）。"""
        sxT, syT = self.total_scale()
        return self.P[1] + (PAD + MOUTH_ROW - self.rig.C[1]) * self.rig.s * syT

    def act_eat(self):
        """白色星星糖果從天上掉下來 → 撿起來 → 捧在嘴邊一口一口吃掉。"""
        U = self.U
        s = self.rig.s
        yield from self.turn_to(0)
        l, t, r, b = self.work
        d = 1 if (r - self.P[0]) > (self.P[0] - l) else -1
        fx = self.P[0] + d * 0.3 * U
        self.say("……糖果。", 1.2)
        # 1. 糖果閃著光掉下來
        fy, vy, bounced = b - 1.3 * U, 0.0, False
        while True:
            vy += self.G * 0.6 * self.dt
            fy += vy * self.dt
            if fy >= self.work[3]:
                fy = self.work[3]
                if not bounced and vy > 0.5 * U:
                    vy, bounced = -vy * 0.3, True
                else:
                    break
            if random.random() < 0.3:
                self.spawn("spark", fx + random.uniform(-4, 4) * s, fy - 6 * s, 0, -0.1 * U, 0, 0.5)
            self.props["food"] = (STAR_CANDY[0], fx, fy, "front")
            self.ground()
            yield
        # 2. 轉過去、彎腰撿起來
        yield from self.turn_to(90 if d > 0 else 270)
        for p in self.over(0.3):
            e = ease(p)
            self.sy = 1 - 0.16 * e
            self.sx = 1 + 0.08 * e
            self.a["lean"] = d * 0.05 * U * e
            self.a["head"] = d * 0.03 * U * e
            self.ground()
            yield
        hand_x = self.P[0] + d * 0.16 * U
        for p in self.over(0.25):  # 糖果移到手上
            e = ease(p)
            cy = self.work[3] + (self.P[1] - self.work[3]) * e * 0.5
            self.props["food"] = (STAR_CANDY[0], fx + (hand_x - fx) * e, cy, "front")
            self.ground()
            yield
        # 3. 站起來、轉正面，捧到嘴邊
        for p in self.over(0.25):
            e = ease(p)
            self.sy = 0.84 + 0.16 * e
            self.sx = 1.08 - 0.08 * e
            self.a["lean"] = d * 0.05 * U * (1 - e)
            self.a["head"] = d * 0.03 * U * (1 - e)
            self.props["food"] = (STAR_CANDY[0], hand_x, self.P[1], "front")
            self.ground()
            yield
        self.sx = self.sy = 1.0
        self.busy_look = True
        self.head_view = None
        yield from self.turn_to(0, 0.08)

        def hold(size_i, lift=0.0):
            my = self.mouth_y()
            candy = STAR_CANDY[size_i]
            cb = my + (candy.height / 2 + 3 - lift) * s
            self.props["food"] = (candy, self.P[0], cb, "front")
            self.props["hands"] = (self.rig.hold_hands, self.P[0], cb + 3 * s, "front")

        for p in self.over(0.3):  # 雙手把糖果捧上來
            hold(0, -6 * (1 - ease(p)))
            self.ground()
            yield
        # 4. 一口、兩口、三口
        for k in range(3):
            for p in self.over(0.18):  # 湊上去咬
                e = math.sin(math.pi * p)
                self.a["head"] = 0.0
                self.sy = 1 - 0.03 * e
                hold(k, 2 * e)
                self.ground()
                yield
            if k == 0:
                self.say("……（嚼嚼）", 1.6)
            nxt = k + 1
            for _ in range(3):
                self.spawn("crumb" if random.random() < 0.5 else "spark", self.P[0] + random.uniform(-3, 3) * s,
                           self.mouth_y() + 4 * s, random.uniform(-0.3, 0.3) * U, -0.2 * U, 2.5 * U, 0.6)
            for p in self.over(0.6):  # 嚼
                self.sy = 1 - 0.025 * abs(math.sin(p * 3 * math.pi))
                if nxt < len(STAR_CANDY):
                    hold(nxt)
                else:
                    self.props.pop("food", None)
                    self.props["hands"] = (self.rig.hold_hands, self.P[0], self.mouth_y() + 9 * s, "front")
                self.ground()
                yield
        self.sy = 1.0
        # 5. 吃完，手放下
        for p in self.over(0.25):
            self.props["hands"] = (self.rig.hold_hands, self.P[0], self.mouth_y() + (9 + 8 * ease(p)) * s, "front")
            self.ground()
            yield
        self.props.pop("hands", None)
        self.props.pop("food", None)
        self.busy_look = False
        if self.care:
            self.care.add("hunger", 35)
            self.care.add("mood", 4)
        self.say(random.choice(LINES["eat"]))
        self.spawn("heart", self.P[0], self.P[1] - 0.45 * U, 0, -0.3 * U, 0, 1.0)
        yield from self.act_idle(0.8, face=False)

    def update_bed(self, show=True):
        if not show:
            self.props.pop("bed", None)
            self.props.pop("bed_front", None)
            return
        if getattr(self, "_bed_key", None) != is_night():
            self._bed_key = is_night()
            self._bed = make_moonflower_bed(0.8 if self._bed_key else 0.0)
        back, front = self._bed
        x = self.bed_x if getattr(self, "bed_x", None) is not None else self.P[0]
        self.props["bed"] = (back, x, self.work[3], "back")
        self.props["bed_front"] = (front, x, self.work[3], "front")  # 前層與後層同尺寸，底部對齊

    def act_sleep(self, max_dur=None):
        U = self.U
        s = self.rig.s
        max_dur = max_dur if max_dur is not None else random.uniform(SLEEP_MIN_S, SLEEP_MAX_S)
        min_dur = min(SLEEP_MIN_S, max_dur)
        yield from self.turn_to(0)
        self.say("……睏。")
        for p in self.over(0.7):  # 打呵欠
            self.sy = 1 + 0.06 * math.sin(math.pi * p)
            self.sx = 1 - 0.04 * math.sin(math.pi * p)
            self.ground()
            yield
        self.sx = self.sy = 1.0
        # 月光花小床開出來
        self.bed_x = self.P[0]
        for _ in range(8):
            self.spawn("spark", self.bed_x + random.uniform(-0.35, 0.35) * U, self.work[3] - random.uniform(0, 8) * s,
                       0, -0.15 * U, 0, 0.9)
        self.update_bed()
        for p in self.over(0.35):
            self.ground()
            yield
        # 爬上床、躺進被子裡（頭在左邊、枕在枕頭上）
        x0, y0 = self.P
        bed_cx, bed_cy = self.bed_x + 2 * s, self.work[3] - (BED_LIFT + 4) * s
        self.clip_y = self.work[3] - BED_LIFT * s
        for p in self.over(0.6):
            e = ease(p)
            self.rot = -90 * e
            self.P[0] = x0 + (bed_cx - x0) * e
            self.P[1] = y0 + (bed_cy - y0) * e - math.sin(math.pi * p) * 0.12 * U
            self.update_bed()
            yield
        self.rot = -90.0
        self.P[0], self.P[1] = bed_cx, bed_cy
        for p in self.over(0.4):  # 把被子拉上來蓋好
            self.quilt_frac = ease(p)
            self.update_bed()
            yield
        self.quilt_frac = 1.0
        self.sleeping, self.wake_req = True, False
        T = zt = 0.0
        while T < max_dur and not self.wake_req and not (
                T > min_dur and self.care and self.care.v["energy"] >= 100):
            T += self.dt
            zt += self.dt
            if zt > 1.6:
                zt = 0.0
                hx, hy = rot2(0, -0.8 * self.rig.dh, self.rot)
                self.spawn("z", self.P[0] + hx, self.P[1] + hy - 0.1 * U, 0.06 * U, -0.25 * U, 0, 2.0)
            self.P[0], self.P[1] = bed_cx, self.work[3] - (BED_LIFT + 4) * s
            self.clip_y = self.work[3] - BED_LIFT * s
            self.update_bed()
            yield
        self.sleeping = False
        self.say("……？" if self.wake_req else "……早。")
        self.wake_req = False
        for p in self.over(0.35):  # 掀開被子
            self.quilt_frac = 1 - ease(p)
            self.update_bed()
            yield
        self.quilt_frac = 0.0
        for p in self.over(0.6):  # 坐起來、下床
            e = ease(p)
            self.rot = -90 * (1 - e)
            self.P[0] = bed_cx + (x0 - bed_cx) * e
            fy = self.work[3] - self.extent()[1]
            self.P[1] = bed_cy + (fy - bed_cy) * e - math.sin(math.pi * p) * 0.12 * U
            if p > 0.6:
                self.clip_y = None
            self.update_bed()
            yield
        self.clip_y = None
        self.rot = 0.0
        for _ in range(6):
            self.spawn("spark", self.bed_x + random.uniform(-0.35, 0.35) * U, self.work[3] - random.uniform(0, 8) * s,
                       0, -0.15 * U, 0, 0.8)
        self.update_bed(False)
        self.bed_x = None
        yield from self.turn_to(0)

    def act_bath(self):
        U = self.U
        yield from self.turn_to(0)
        self.say("……洗澡。")
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
        self.say("……甩。", 1.2)
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
        self.say("……乾淨了。")
        yield from self.act_idle(0.8, face=False)

    def act_trip(self):
        U = self.U
        if self.view not in self.rig.legs:
            yield from self.turn_to(random.choice([90, 270]))
        d = self.facing()
        self.say("……！", 1.0)
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
            self.say("……沒有窗戶。")
            yield from self.act_idle(1.0, face=False)
            return
        cands.sort(key=lambda c: c[0])
        _, hwnd, side = random.choice(cands[:3])
        self.say("……爬。")

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
                self.say("……！", 1.0)
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
        self.say("……上來了。")
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
        self.say("……", 1.2)
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
    try:  # 讓工作列用我們自己的月光花圖示，而不是 Python 的
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("DreamGod.L2DPet")
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
    def log_error(*_args):
        """打包成 exe（沒有主控台）時，把錯誤寫到 %APPDATA%/DreamGodL2D/error.log。"""
        import traceback

        try:
            path = Path(os.environ.get("APPDATA", str(APP_DIR))) / "DreamGodL2D" / "error.log"
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "a", encoding="utf-8") as fp:
                fp.write(time.strftime("%Y-%m-%d %H:%M:%S ") + traceback.format_exc() + "\n")
        except Exception:
            pass

    root = tk.Tk()
    root.report_callback_exception = lambda *a: log_error()
    root.title(f"{PET_NAME}（夢境神明） L2D 桌寵")
    # 所有視窗（山谷、對話框）的圖示都換成月光花
    icons = [ImageTk.PhotoImage(moonflower_icon(n), master=root) for n in (16, 32, 48, 64)]
    root.iconphoto(True, *icons)
    root._moonflower_icons = icons
    pet_win = LWin(root)

    data_dir = Path(os.environ.get("APPDATA", str(ROOT))) / "DreamGodL2D"
    state = {"press": None, "dragged": False, "skip_release": False, "last": time.perf_counter(),
             "topmost_t": 0.0, "garden_t": 0.0, "home_t": 0.0}
    base_sprites = build_pixel_sprites()
    outfit_save = data_dir / "outfit.json"
    try:
        outfit = json.loads(outfit_save.read_text(encoding="utf-8"))["outfit"]
        if outfit not in OUTFITS:
            outfit = DEFAULT_OUTFIT
    except Exception:
        outfit = DEFAULT_OUTFIT
    sprites = dress_all(base_sprites, outfit)
    rig = Rig(SCALE, sprites, sleeve_colors(outfit))
    pet = Pet(rig, work_area)
    cur = {"outfit": outfit, "sprites": sprites}
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

    # ---- 聲音（Windows 內建 winsound 播放合成好的 wav）
    sound = {"on": True}

    def wav_file(name, data):
        import wave

        path = data_dir / f"{name}.wav"
        if not path.exists():
            data_dir.mkdir(parents=True, exist_ok=True)
            with wave.open(str(path), "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(SAMPLE_RATE)
                wf.writeframes(data)
        return path

    def play_sound(name):
        try:
            import winsound

            if name is None or not sound["on"]:
                winsound.PlaySound(None, 0)
                return
            data = (HARP_TUNE if name == "harp" else DANCE_TUNE)[0]
            winsound.PlaySound(str(wav_file(f"music_{name}", data)), winsound.SND_FILENAME | winsound.SND_ASYNC)
        except Exception:
            pass

    pet.on_sound = play_sound

    # ---- 玩具：月光花花束（可以拖、會掉下來）
    class ToyBox:
        def __init__(self):
            self.items = []  # (Toy, LWin, state)

        def add(self, kind):
            if any(tt.kind == kind for tt, _w, _s in self.items):
                pet.say("……已經有了。", 1.2)
                return
            l, t, r, b = pet.base_work
            x = min(max(pet.P[0] + random.choice([-1, 1]) * 0.8 * pet.U, l + 40), r - 40)
            toy = Toy(kind, x, t + 0.3 * (b - t))
            win = LWin(tk.Toplevel(root))
            st = {"key": None, "drag": None, "last": None, "v": (0.0, 0.0)}
            win.win.bind("<ButtonPress-1>", lambda _e, toy=toy, st=st: self.press(toy, st))
            win.win.bind("<B1-Motion>", lambda _e, toy=toy, st=st: self.motion(toy, st))
            win.win.bind("<ButtonRelease-1>", lambda _e, toy=toy, st=st: self.release(toy, st))
            self.items.append((toy, win, st))
            pet.toys.append(toy)
            pet_win.raise_top()

        def clear(self):
            for toy, win, _st in self.items:
                win.destroy()
            self.items.clear()
            pet.toys.clear()

        def press(self, toy, st):
            mx, my = cursor()
            toy.held = True
            st["drag"] = (toy.x - mx, toy.y - my)
            st["last"] = (mx, my, time.perf_counter())
            st["v"] = (0.0, 0.0)

        def motion(self, toy, st):
            if not st["drag"]:
                return
            mx, my = cursor()
            now = time.perf_counter()
            lx, ly, lt = st["last"]
            dt = max(now - lt, 1e-3)
            st["v"] = (0.6 * st["v"][0] + 0.4 * (mx - lx) / dt, 0.6 * st["v"][1] + 0.4 * (my - ly) / dt)
            st["last"] = (mx, my, now)
            toy.x, toy.y = mx + st["drag"][0], my + st["drag"][1]

        def release(self, toy, st):
            if not st["drag"]:
                return
            st["drag"] = None
            toy.held = False
            lim = 5 * pet.U
            toy.vx = max(-lim, min(lim, st["v"][0]))
            toy.vy = max(-lim, min(lim, st["v"][1]))

        def update(self, dt):
            for toy, win, st in self.items:
                toy.step(dt, work_area((toy.x, toy.y - 10)), pet.G)
                if toy.carried:
                    if st["key"] != "hidden":
                        win.push(EMPTY, -3000, -3000)
                        st["key"] = "hidden"
                    continue
                img = toy.image()
                key = (int(toy.x), int(toy.y))
                if key != st["key"]:
                    st["key"] = key
                    win.push(img, toy.x - img.width * SCALE / 2, toy.y - img.height * SCALE, SCALE)

    toybox = ToyBox()


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
        w, h = img.width * BUBBLE_SCALE, img.height * BUBBLE_SCALE
        l, t, r, b = pet.base_work
        x = min(max(pet.P[0] - w / 2, l), r - w)
        y = max(pet.P[1] + pet.extent()[0] - h + 4, t)
        bubble.push(img, x, y, BUBBLE_SCALE)
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
        "dance": pet.act_dance, "harp": pet.act_harp, "plush": pet.act_hug_plush,
        "wish": pet.act_wish,
    }

    def do_action(name):
        if name == "wake":
            if pet.sleeping:
                pet.wake_req = True
            else:
                pet.say("……醒著。")
            return
        if name == "sleep" and pet.sleeping:
            return
        if name == "talk":  # 打開山谷，跟她對話
            open_home()
            root.after(300, lambda: main_menu("……你來了。"))
            return
        if name == "toys_off":
            toybox.clear()
            return
        if name == "toy_plush":
            toybox.add("plush")
            return
        if name == "plush" and not any(tt.kind == "plush" for tt in pet.toys):
            toybox.add("plush")
        if name == "outfit":
            names = list(OUTFITS)
            set_outfit(names[(names.index(cur["outfit"]) + 1) % len(names)])
            return
        if name in ("game", "stars"):
            open_game("cloud" if name == "game" else "stars")
            return
        if name == "jump_down" and not pet.platform:
            pet.say("……在地上。")
            return
        if name == "climb" and pet.platform:
            pet.say("……在上面了。")
            return
        pet.run(actions[name]())

    def talk(text):
        reply, act = respond(text)
        pet.say(reply)
        if dlg["on"]:
            dlg_say(reply, then=main_menu)
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
        w.title(f"跟{PET_NAME}說話")
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
    # 狀態條統一月光淡紫（跟山谷夜色／邊框同一色系）
    _BAR = (210, 190, 255)
    bar_colors = {"hunger": _BAR, "clean": _BAR, "mood": _BAR, "energy": _BAR}

    def open_home():
        if home["win"] is not None and home["win"].winfo_exists():
            home["win"].deiconify()
            home["win"].lift()
            return
        w = tk.Toplevel(root)
        w.title(f"無夢之夢・月光花山谷 — {PET_NAME}")
        w.configure(bg="#06060a")
        w.resizable(False, False)
        cv = tk.Canvas(w, width=VW * HS, height=VH * HS, highlightthickness=0, bg="#000000", cursor="hand2")
        cv.pack()
        cv.bind("<ButtonPress-1>", valley_press)
        cv.bind("<KeyPress>", dlg_key)
        cv.bind("<Motion>", valley_motion)
        cv.bind("<B1-Motion>", valley_motion)
        cv.bind("<ButtonRelease-1>", valley_release)
        btns = tk.Frame(w, bg="#06060a")
        btns.pack(fill="x", padx=4, pady=(4, 1))
        for i, (label, act) in enumerate((("餵食", "eat"), ("洗澡", "bath"), ("睡覺", "sleep"), ("叫醒", "wake"),
                                          ("爬視窗", "climb"), ("跳下來", "jump_down"), ("種花", "plant"),
                                          ("跌倒", "trip"), ("雲端之夢", "game"), ("接星星", "stars"),
                                          ("跳舞", "dance"), ("彈豎琴", "harp"),
                                          ("抱花束", "plush"), ("收花束", "toys_off"), ("許願", "wish"))):
            tk.Button(btns, text=label, command=(lambda a=act: do_action(a)),
                      bg="#17142a", fg="#e8e4ff",
                      activebackground="#2c2840", activeforeground="#ffffff", relief="flat", pady=0,
                      font=("Microsoft JhengHei UI", 9)).grid(row=i // 5, column=i % 5, padx=1, pady=1, sticky="ew")
        for c in range(4):
            btns.grid_columnconfigure(c, weight=1)
        btns.grid_columnconfigure(4, weight=1)
        orow = tk.Frame(w, bg="#06060a")
        orow.pack(fill="x", padx=4, pady=(1, 1))
        tk.Label(orow, text="換裝", bg="#06060a", fg="#e8e4ff", font=("Microsoft JhengHei UI", 9)).pack(side="left")
        om = tk.OptionMenu(orow, outfit_var, *OUTFITS.keys(), command=lambda n: set_outfit(n))
        om.configure(bg="#17142a", fg="#e8e4ff", activebackground="#2c2840", activeforeground="#ffffff",
                     relief="flat", highlightthickness=0, font=("Microsoft JhengHei UI", 9))
        om["menu"].configure(bg="#17142a", fg="#e8e4ff", font=("Microsoft JhengHei UI", 9))
        om.pack(side="left", fill="x", expand=True, padx=(4, 0))
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
            dlg.update(on=False)
            w.destroy()
            home["win"] = None

        w.protocol("WM_DELETE_WINDOW", close)
        home.update(win=w, canvas=cv)
        render_home()

    # ---- 小遊戲：雲端之夢／接星星（共用一套視窗）
    game = {"win": None, "photo": None, "sprites": None, "kind": None}
    GS = 2
    game_save = data_dir / "game.json"
    GAMES = {"cloud": CloudGame, "stars": StarCatchGame}

    def load_bests():
        try:
            d = json.loads(game_save.read_text(encoding="utf-8"))
            if "best" in d and "best_cloud" not in d:  # 舊存檔
                d["best_cloud"] = d.pop("best")
            return d
        except Exception:
            return {}

    unity = {"proc": None, "result": data_dir / "unity_result.json", "kind": None}

    def open_unity_game(kind):
        """Unity 版小遊戲（unity/Build/DreamGodGames.exe）：帶入目前的衣服，關掉後讀成績。"""
        import subprocess

        if unity["proc"] is not None and unity["proc"].poll() is None:
            pet.say("……已經在玩了。", 1.4)
            return True
        try:
            unity["result"].unlink(missing_ok=True)
            outfit_idx = list(OUTFITS).index(cur["outfit"])
            # 打包成無主控台的 exe 時沒有有效的標準輸入輸出，要明確導到 DEVNULL
            unity["proc"] = subprocess.Popen([str(UNITY_EXE), "-game", kind, "-outfit", str(outfit_idx),
                                              "-result", str(unity["result"])], cwd=str(UNITY_EXE.parent),
                                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                             stderr=subprocess.DEVNULL)
            unity["kind"] = kind
            pet.say("……上去。" if kind == "cloud" else "……接星星。", 1.4)
            return True
        except Exception:
            log_error()
            return False

    def check_unity_game():
        pr = unity["proc"]
        if pr is None or pr.poll() is None:
            return
        unity["proc"] = None
        try:
            rounds = json.loads(unity["result"].read_text(encoding="utf-8")).get("rounds", [])
        except Exception:
            rounds = []
        if not rounds:
            return
        mood = 0
        for r in rounds:
            if r.get("game") == "cloud":
                mood += 2 + int(r.get("score", 0)) // 30 + int(r.get("stars", 0))
            else:
                mood += 2 + int(r.get("score", 0)) // 4
                if pet.care:
                    pet.care.add("hunger", min(10, int(r.get("score", 0)) // 3))
        if pet.care:
            pet.care.add("mood", min(20, mood))
        last = rounds[-1]
        if last.get("game") == "cloud":
            pet.say("……雲上，很漂亮。" if any(r.get("reached") for r in rounds) else "……掉下來了。")
        else:
            pet.say(f"……接到{last.get('score', 0)}顆。")

    def open_game(kind="cloud"):
        if UNITY_EXE.exists() and open_unity_game(kind):
            return
        if game["win"] is not None and game["win"].winfo_exists():
            if game["kind"] == kind:
                game["win"].deiconify()
                game["win"].lift()
                game["win"].focus_force()
                return
            game["win"].destroy()
        if game["sprites"] is None:
            game["sprites"] = make_small_sprites(cur["sprites"])
        cls = GAMES[kind]
        w = tk.Toplevel(root)
        w.title(cls.TITLE)
        w.configure(bg="#06060a")
        w.resizable(False, False)
        cv = tk.Canvas(w, width=cls.W * GS, height=cls.H * GS, highlightthickness=0, bg="#000000")
        cv.pack()
        tk.Label(w, text=cls.HELP, bg="#06060a", fg="#b8b4d8", font=("Microsoft JhengHei UI", 9)).pack(pady=(2, 4))
        g = cls(game["sprites"], int(load_bests().get(cls.SAVE_KEY, 0)))
        keys = set()
        w.bind("<KeyPress>", lambda e: keys.add(e.keysym.lower()))
        w.bind("<KeyRelease>", lambda e: keys.discard(e.keysym.lower()))
        w.bind("<space>", lambda _e: g.click())
        cv.bind("<Motion>", lambda e: setattr(g, "mouse", e.x / GS))
        cv.bind("<Leave>", lambda _e: setattr(g, "mouse", None))
        cv.bind("<Button-1>", lambda _e: g.click())
        game.update(win=w, kind=kind)
        pet.say("……上去。" if kind == "cloud" else "……接星星。", 1.4)

        def game_over():
            d = load_bests()
            d[cls.SAVE_KEY] = g.best
            try:
                game_save.parent.mkdir(parents=True, exist_ok=True)
                game_save.write_text(json.dumps(d), encoding="utf-8")
            except Exception:
                pass
            if pet.care:
                if kind == "cloud":
                    pet.care.add("mood", min(12, 2 + g.meters // 30 + g.stars))
                    pet.say("……雲上，很漂亮。" if g.reached else "……掉下來了。")
                else:
                    pet.care.add("mood", min(12, 2 + g.score // 4))
                    pet.care.add("hunger", min(10, g.score // 3))
                    pet.say(f"……接到{g.score}顆。")

        def loop():
            if not w.winfo_exists():
                if game["win"] is w:
                    game["win"] = None
                return
            dx = (1 if keys & {"right", "d"} else 0) - (1 if keys & {"left", "a"} else 0)
            if dx:
                g.mouse = None
            g.step(1 / 30, dx)
            if g.just_over:
                game_over()
            ph = ImageTk.PhotoImage(g.render().resize((cls.W * GS, cls.H * GS), Image.NEAREST))
            cv.delete("all")
            cv.create_image(0, 0, anchor="nw", image=ph)
            game["photo"] = ph
            w.after(33, loop)

        w.focus_force()
        loop()

    # ---- 換裝
    def set_outfit(name, animate=True):
        if name not in OUTFITS:
            return
        cur["outfit"] = name
        cur["sprites"] = dress_all(base_sprites, name)
        pet.set_rig(Rig(SCALE, cur["sprites"], sleeve_colors(name)))
        game["sprites"] = None
        try:
            outfit_save.parent.mkdir(parents=True, exist_ok=True)
            outfit_save.write_text(json.dumps({"outfit": name}, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass
        if outfit_var.get() != name:
            outfit_var.set(name)
        if animate:
            pet.run(pet.act_change())

    outfit_var = tk.StringVar(value=cur["outfit"])

    # ---- 山谷裡的 RPG 對話（參考養成遊戲：大張立繪＋對話框＋選項）
    dlg = {"on": False, "text": "", "t0": 0.0, "choices": [], "sel": 0, "then": None, "rects": []}
    TYPE_CPS = 22.0  # 打字速度（字／秒）

    def dlg_say(text, choices=None, then=None):
        dlg.update(on=True, text=text, t0=time.perf_counter(), choices=choices or [], sel=0, then=then, rects=[])
        render_home()

    def dlg_shown():
        return min(len(dlg["text"]), int((time.perf_counter() - dlg["t0"]) * TYPE_CPS))

    def dlg_close():
        dlg.update(on=False, choices=[], then=None)
        render_home()

    def main_menu(prompt="……還有嗎？"):
        dlg_say(prompt, [("最近好嗎？", ask_status), ("說說夢的事", ask_dream), ("一起玩吧", ask_play),
                         ("（摸摸頭）", do_pat), ("再見", say_bye)])

    def ask_status():
        c = pet.care.v if pet.care else {}
        if c.get("hunger", 100) < 30:
            line = "……肚子有點餓。星星糖……可以嗎？"
        elif c.get("energy", 100) < 30:
            line = "……有點睏。"
        elif c.get("clean", 100) < 30:
            line = "……想洗澡。"
        elif c.get("mood", 100) < 40:
            line = "……還好。……陪我一下就好。"
        else:
            line = "……還好。夢很安靜。"
        if pet.care:
            pet.care.add("mood", 2)
        dlg_say(line, then=main_menu)

    def ask_dream():
        if pet.care:
            pet.care.add("mood", 3)
        dlg_say(random.choice(DREAM_TALK), then=main_menu)

    def ask_play():
        def go(name):
            return lambda: (dlg_say("……好。", then=lambda: (dlg_close(), do_action(name))))
        dlg_say("……玩什麼？", [("跳舞", go("dance")), ("彈豎琴", go("harp")),
                              ("抱花束", go("plush")), ("許願", go("wish")),
                              ("算了", lambda: main_menu("……嗯。"))])

    def do_pat():
        if pet.care:
            pet.care.add("mood", 4)
        pet.spawn("heart", pet.P[0], pet.P[1] - 0.45 * pet.U, 0, -0.3 * pet.U, 0, 1.0)
        dlg_say(random.choice(["…………", "……頭髮會亂掉。", "……再一下下。", "……（閉上眼睛）"]), then=main_menu)

    def say_bye():
        dlg_say("……嗯。再見。", then=dlg_close)

    def dlg_advance():
        if not dlg["on"]:
            return
        if dlg_shown() < len(dlg["text"]):
            dlg["t0"] = 0.0  # 先把字全部顯示出來
            render_home()
            return
        if dlg["choices"]:
            _label, fn = dlg["choices"][dlg["sel"]]
            fn()
            return
        then = dlg["then"]
        if then:
            then()
        else:
            dlg_close()

    def dlg_hit(vx, vy):
        for i, (x0, y0, x1, y1) in enumerate(dlg["rects"]):
            if x0 <= vx <= x1 and y0 <= vy <= y1:
                return i
        return None

    def dlg_key(e):
        if not dlg["on"]:
            return
        k = e.keysym
        if k in ("Up", "w") and dlg["choices"]:
            dlg["sel"] = (dlg["sel"] - 1) % len(dlg["choices"])
            render_home()
        elif k in ("Down", "s") and dlg["choices"]:
            dlg["sel"] = (dlg["sel"] + 1) % len(dlg["choices"])
            render_home()
        elif k in ("Return", "space", "z"):
            dlg_advance()
        elif k == "Escape":
            dlg_close()

    # ---- 在山谷裡點她開對話；按住拖動才是抓起來移動（對應回桌面上的位置）
    vdrag = {"on": False, "press": None}

    def valley_to_screen(vx, vy):
        l, t, r, b = pet.base_work
        floor_y = int(VH * 0.86)
        return (l + (vx - 26) / (VW - 52) * (r - l), pet.work[3] - (floor_y - vy) * rig.s)

    def valley_press(e):
        vx, vy = e.x / HS, e.y / HS
        home["canvas"].focus_set()
        if dlg["on"]:
            if dlg["choices"] and dlg_shown() >= len(dlg["text"]):
                i = dlg_hit(vx, vy)
                if i is not None:
                    dlg["sel"] = i
                    dlg_advance()
                return
            dlg_advance()
            return
        cx, cy = home.get("pet_xy", (-99, -99))
        if abs(vx - cx) < 18 and abs(vy - cy) < 30:
            vdrag["press"] = (vx, vy)

    def valley_motion(e):
        vx, vy = e.x / HS, e.y / HS
        if dlg["on"]:
            if dlg["choices"]:
                i = dlg_hit(vx, vy)
                if i is not None and i != dlg["sel"]:
                    dlg["sel"] = i
                    render_home()
            return
        if vdrag["press"] and not vdrag["on"]:
            px, py = vdrag["press"]
            if abs(vx - px) + abs(vy - py) > 3:
                vdrag["on"] = True
                pet.grab(*valley_to_screen(px, py))
                pet.say("……！", 1.0)
        if vdrag["on"]:
            pet.drag_to(*valley_to_screen(vx, vy))

    def valley_release(_e):
        if vdrag["on"]:
            vdrag["on"] = False
            pet.release()
        elif vdrag["press"] and not dlg["on"]:
            main_menu("……你來了。")
        vdrag["press"] = None

    def draw_dialog(bg):
        """養成遊戲風的對話畫面：背景變暗、右側左 45 度的大張立繪、底部對話框、名牌、選項。"""
        dim = Image.new("RGBA", bg.size, (4, 4, 12, 120))
        bg.alpha_composite(dim)
        # 立繪：靜止（關掉頭髮／裙子／呼吸／翅膀等物理晃動）
        p = pet.params()
        p.update(gait=0.0, stride=0.0, look_x=0.0, look_y=0.0, head_view=None,
                 lean=0.0, legs=0.0, head=0.0, hair=0.0, skirt=0.0, flare=0.0,
                 breath=0.0, wing=0.0, wing_flap=1.0)
        por = rig.render(("fl", False), p, 0, 1, 1)
        box = por.getbbox()
        if box:
            por = por.crop(box)
            por = por.resize((por.width * 2, por.height * 2), Image.NEAREST)
            bx = VW - por.width + 14
            by = VH - 46 - int(por.height * 0.62)
            bg.paste(por, (bx, by), por)
        d = ImageDraw.Draw(bg)
        d.fontmode = "1"
        font = pixel_font(11)
        # 對話框（雙框）＋名牌
        x0, y0, x1, y1 = 4, VH - 44, VW - 4, VH - 3
        d.rectangle((x0, y0, x1, y1), fill=(14, 14, 34, 255), outline=(150, 140, 200, 255))
        d.rectangle((x0 + 2, y0 + 2, x1 - 2, y1 - 2), outline=(70, 64, 110, 255))
        d.rectangle((8, y0 - 12, 50, y0 + 1), fill=(36, 30, 66, 255), outline=(150, 140, 200, 255))
        d.text((12, y0 - 11), PET_NAME, font=font, fill=(255, 248, 206, 255))
        shown = dlg_shown()
        lines = _wrap(dlg["text"][:shown], 16)[:3]
        for i, ln in enumerate(lines):
            d.text((10, y0 + 5 + i * 12), ln, font=font, fill=(236, 232, 255, 255))
        done = shown >= len(dlg["text"])
        if done and not dlg["choices"] and int(time.perf_counter() * 2.5) % 2:
            d.polygon([(x1 - 12, y1 - 9), (x1 - 6, y1 - 9), (x1 - 9, y1 - 5)], fill=(255, 248, 206, 255))
        # 選項（左上方的選單）
        dlg["rects"] = []
        if done and dlg["choices"]:
            n = len(dlg["choices"])
            w = 8 + max(int(d.textlength(lb, font=font)) for lb, _ in dlg["choices"]) + 14
            cy0 = y0 - 16 - n * 13
            d.rectangle((6, cy0 - 3, 6 + w, y0 - 15), fill=(14, 14, 34, 255), outline=(150, 140, 200, 255))
            for i, (lb, _fn) in enumerate(dlg["choices"]):
                yy = cy0 + i * 13
                sel = i == dlg["sel"]
                if sel:
                    d.rectangle((8, yy - 1, 4 + w, yy + 11), fill=(52, 44, 96, 255))
                    d.polygon([(10, yy + 2), (10, yy + 8), (14, yy + 5)], fill=(255, 248, 206, 255))
                d.text((17, yy), lb, font=font, fill=(255, 248, 206, 255) if sel else (206, 200, 236, 255))
                dlg["rects"].append((6, yy - 1, 6 + w, yy + 11))

    def render_home():
        if home["win"] is None:
            return
        # 對話中凍結山谷時間，花／星光也不晃
        t = home.get("dlg_t", pet.t) if dlg["on"] else pet.t
        if dlg["on"] and "dlg_t" not in home:
            home["dlg_t"] = pet.t
            t = home["dlg_t"]
        if not dlg["on"]:
            home.pop("dlg_t", None)
        bg = draw_valley(t, VW, VH)
        # 山谷裡的她＝桌面上的她：同一個畫格（吃飯、洗澡、跌倒、睡覺、翻滾、倒吊…都同步），
        # 在桌面上的左右位置對應到山谷裡的左右位置，離地高度也照比例（太高就停在山谷頂端）
        img, _, _ = pet.frame()
        if dlg["on"]:
            img = Image.new("RGBA", img.size, (0, 0, 0, 0))
        s_ = rig.s
        l, t, r, b = pet.base_work
        floor_y = int(VH * 0.86)
        above = (pet.work[3] - pet.P[1]) / s_  # 中心離地面多高（點陣格）
        cx = 26 + (pet.P[0] - l) / max(r - l, 1) * (VW - 52)
        cy = max(floor_y - above, 22)
        ox, oy = int(round(cx - WIN_N / 2)), int(round(cy - WIN_N / 2))
        bg.paste(img, (ox, oy), img)
        home["pet_xy"] = (cx, cy)
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
        if dlg["on"]:
            draw_dialog(bg)
        # 說話泡泡
        elif pet.speech:
            bb = render_bubble(pet.speech[0], 11)
            head_y = cy + pet.extent()[0] / s_
            bg.alpha_composite(bb, (int(max(0, min(VW - bb.width, cx - bb.width / 2))),
                                    int(max(0, head_y - bb.height))))
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
            pet.say("……放我下來。", 1.4)
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
            pet.run(pet.act_tilt())
        state["dragged"] = False

    def on_double(_e):
        state["skip_release"] = True
        open_home()

    # ---- 右鍵選單
    menu = tk.Menu(root, tearoff=0)
    auto_var = tk.BooleanVar(value=True)
    look_var = tk.BooleanVar(value=True)
    sound_var = tk.BooleanVar(value=True)
    follow_var = tk.BooleanVar(value=True)

    def do(name):
        return lambda: do_action(name)

    menu.add_command(label="打開月光花山谷", command=open_home)
    menu.add_command(label="跟她說話…", command=open_chat)
    menu.add_command(label="在山谷裡對話", command=do("talk"))
    menu.add_command(label="小遊戲：雲端之夢", command=lambda: open_game("cloud"))
    menu.add_command(label="小遊戲：接星星", command=lambda: open_game("stars"))
    menu.add_separator()
    menu.add_command(label="餵食", command=do("eat"))
    menu.add_command(label="洗澡", command=do("bath"))
    menu.add_command(label="睡覺", command=do("sleep"))
    menu.add_command(label="叫醒", command=do("wake"))
    menu.add_command(label="爬視窗", command=do("climb"))
    menu.add_command(label="從視窗跳下來", command=do("jump_down"))
    menu.add_command(label="跌倒", command=do("trip"))
    menu.add_command(label="跳舞", command=do("dance"))
    menu.add_command(label="彈豎琴", command=do("harp"))
    menu.add_command(label="許願", command=do("wish"))
    toys_menu = tk.Menu(menu, tearoff=0)
    toys_menu.add_command(label="拿出月光花花束", command=do("toy_plush"))
    toys_menu.add_command(label="讓她抱花束", command=do("plush"))
    toys_menu.add_separator()
    toys_menu.add_command(label="收起花束", command=lambda: toybox.clear())
    menu.add_cascade(label="花束", menu=toys_menu)
    menu.add_separator()
    more = tk.Menu(menu, tearoff=0)
    for label, name in (("往左走", "walk_l"), ("往右走", "walk_r"), ("轉一圈", "spin"), ("東張西望", "look"),
                        ("彈跳", "bounce"), ("前空翻", "frontflip"), ("側翻", "somersault"), ("倒吊", "hang"),
                        ("種月光花", "plant")):
        more.add_command(label=label, command=do(name))
    menu.add_cascade(label="更多動作", menu=more)
    wardrobe = tk.Menu(menu, tearoff=0)
    for name in OUTFITS:
        wardrobe.add_radiobutton(label=name, value=name, variable=outfit_var, command=lambda n=name: set_outfit(n))
    menu.add_cascade(label="換裝", menu=wardrobe)
    menu.add_command(label="清除所有花", command=lambda: garden.clear())
    menu.add_separator()

    def toggle_auto():
        pet.auto = auto_var.get()

    def toggle_look():
        pet.look_enabled = look_var.get()

    def toggle_follow():
        pet.follow_enabled = follow_var.get()

    def quit_app():
        play_sound(None)
        garden.save()
        if pet.care:
            pet.care.save()
        root.destroy()

    menu.add_checkbutton(label="視線跟著滑鼠", variable=look_var, command=toggle_look)

    def toggle_sound():
        sound["on"] = sound_var.get()
        if not sound["on"]:
            play_sound(None)

    menu.add_checkbutton(label="聲音", variable=sound_var, command=toggle_sound)
    menu.add_checkbutton(label="跟著滑鼠走", variable=follow_var, command=toggle_follow)
    menu.add_checkbutton(label="自動行動", variable=auto_var, command=toggle_auto)
    autostart_var = tk.BooleanVar(value=autostart_enabled())

    def toggle_autostart():
        ok = set_autostart(autostart_var.get())
        autostart_var.set(autostart_enabled())
        if ok:
            pet.say("……開機就會見到我。" if autostart_var.get() else "……嗯。", 1.6)

    menu.add_checkbutton(label="開機自動啟動", variable=autostart_var, command=toggle_autostart)
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
            toybox.update(dt)
            pet.step(dt)
            img, x, y = pet.frame()
            pet_win.push(img, x, y, rig.s)
            update_bubble()
            state["garden_t"] += dt
            if state["garden_t"] > 0.15:
                state["garden_t"] = 0.0
                garden.update(pet.t)
                check_unity_game()
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
            log_error()
        spent = (time.perf_counter() - now) * 1000
        root.after(max(1, int(33 - spent)), tick)

    root.after(10, tick)
    if "--home" in sys.argv:
        root.after(600, open_home)
    if "--do" in sys.argv:  # 測試用：啟動後直接做某個動作，例如 --do eat
        i = sys.argv.index("--do")
        if i + 1 < len(sys.argv) and (sys.argv[i + 1] in actions or sys.argv[i + 1] in ("game", "stars", "wake", "outfit", "talk",
                                                                       "toy_plush")):
            root.after(2500, lambda: do_action(sys.argv[i + 1]))
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


# ------------------------------------------------------------------ 開機自動啟動
STARTUP_LNK = (Path(os.environ.get("APPDATA", str(ROOT))) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
               / "Startup" / "朵莉姆 L2D 桌寵.lnk")


def autostart_enabled() -> bool:
    return STARTUP_LNK.exists()


def set_autostart(on: bool) -> bool:
    """開機自動啟動：在 Windows 啟動資料夾放（或移除）一個執行 l2d_pet.pyw 的捷徑。"""
    import subprocess

    if not on:
        try:
            STARTUP_LNK.unlink()
        except OSError:
            pass
        return True
    if FROZEN:  # 打包版：直接啟動 exe（圖示就是 exe 本身的月光花）
        target, args, ico = Path(sys.executable), "", Path(sys.executable)
    else:
        exe = Path(sys.executable)
        target = exe.with_name("pythonw.exe") if exe.with_name("pythonw.exe").exists() else exe
        args = f'"{ROOT / "l2d_pet.pyw"}"'
        ico = ROOT / "assets" / "icons" / "moonflower.ico"

    def q(x):
        return str(x).replace("'", "''")

    ps = (f"$s=New-Object -ComObject WScript.Shell; $l=$s.CreateShortcut('{q(STARTUP_LNK)}'); "
          f"$l.TargetPath='{q(target)}'; $l.Arguments='{q(args)}'; "
          f"$l.WorkingDirectory='{q(APP_DIR)}'; $l.IconLocation='{q(ico)},0'; "
          f"$l.Description='{PET_NAME}（夢境神明）桌寵'; $l.Save()")
    try:
        STARTUP_LNK.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=True,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return STARTUP_LNK.exists()
    except Exception:
        return False


# ------------------------------------------------------------------ 匯出給 Unity 小遊戲
UNITY_PROJECT = ROOT / "unity" / "DreamGodGames"
UNITY_EXE = APP_DIR / "unity" / "Build" / "DreamGodGames.exe"


def export_unity(project: Path = UNITY_PROJECT):
    """把點陣角色（每套衣服）、翅膀、星星糖、月光花、平台等輸出到 Unity 的 Resources。"""
    res = project / "Assets" / "Resources" / "Pixel"
    res.mkdir(parents=True, exist_ok=True)
    base = build_pixel_sprites()
    names = list(OUTFITS)
    for i, name in enumerate(names):
        d = res / f"outfit{i}"
        d.mkdir(exist_ok=True)
        sp = dress_all(base, name)
        for k in ("front", "left", "right"):
            sp[k].save(d / f"{k}.png")
            shrink_pixel_sprite(sp[k]).save(d / f"{k}32.png")
    (project / "Assets" / "Resources" / "outfits.json").write_text(
        json.dumps({"names": names}, ensure_ascii=False), encoding="utf-8")
    w, root = make_fairy_wing()
    Image.fromarray(w).save(res / "wing.png")
    Image.fromarray(w).resize((w.shape[1] // 2, w.shape[0] // 2), Image.NEAREST).save(res / "wing32.png")
    for i, c in enumerate(STAR_CANDY):
        c.save(res / f"star{i}.png")
    draw_moonflower(4).save(res / "moonflower.png")
    draw_moonflower(4, 0, 1.0).save(res / "moonflower_glow.png")
    # 平台與道具（和 Python 版小遊戲同樣的畫法）
    leaf = Image.new("RGBA", (32, 7), (0, 0, 0, 0))
    d = ImageDraw.Draw(leaf)
    d.ellipse((0, 0, 31, 6), fill=(36, 62, 42, 255))
    d.ellipse((1, 1, 30, 5), fill=(98, 150, 84, 255))
    d.line((3, 3, 28, 3), fill=(146, 192, 118, 255))
    leaf.putpixel((16, 0), (246, 246, 238, 255))
    leaf.save(res / "leaf.png")
    for nm, col in (("cloud", (240, 242, 252, 255)), ("cloud_move", (214, 226, 250, 255))):
        cl = Image.new("RGBA", (32, 9), (0, 0, 0, 0))
        d = ImageDraw.Draw(cl)
        for x in range(0, 32, 6):
            d.ellipse((x - 1, 0, x + 7, 7), fill=col)
        d.rectangle((2, 3, 29, 7), fill=col)
        d.line((3, 8, 28, 8), fill=(180, 186, 214, 255))
        cl.save(res / f"{nm}.png")
    bub = Image.new("RGBA", (22, 13), (0, 0, 0, 0))
    d = ImageDraw.Draw(bub)
    d.ellipse((0, 0, 21, 12), outline=(176, 214, 244, 255), fill=(214, 236, 255, 70))
    bub.putpixel((5, 3), (255, 255, 255, 255))
    bub.save(res / "bubble.png")
    nm = Image.new("RGBA", (12, 12), (0, 0, 0, 0))
    d = ImageDraw.Draw(nm)
    d.ellipse((0, 0, 11, 11), fill=(52, 24, 70, 255), outline=(120, 70, 150, 255))
    nm.putpixel((4, 5), (255, 120, 160, 255))
    nm.putpixel((7, 5), (255, 120, 160, 255))
    nm.save(res / "nightmare.png")
    PARTICLES["heart"].save(res / "heart.png")
    PARTICLES["spark"].save(res / "spark.png")
    px = Image.new("RGBA", (1, 1), (255, 255, 255, 255))
    px.save(res / "pixel.png")
    moonflower_icon(128).save(res / "icon.png")
    fonts = project / "Assets" / "Resources" / "Fonts"
    fonts.mkdir(parents=True, exist_ok=True)
    (fonts / "Cubic_11.ttf").write_bytes(FONT_PATH.read_bytes())
    print(f"已匯出 Unity 素材到 {res}")


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "--demo":
        run_demo(sys.argv[2])
    elif len(sys.argv) >= 3 and sys.argv[1] == "--autostart":
        print("開機自動啟動：" + ("已開啟" if set_autostart(sys.argv[2] == "on") and autostart_enabled() else "已關閉"))
    elif len(sys.argv) >= 2 and sys.argv[1] == "--export-unity":
        export_unity()
    elif len(sys.argv) >= 2 and sys.argv[1] == "--rebuild-sprites":
        build_pixel_sprites(force=True)
        print(f"已重新產生點陣圖：{PIXEL_DIR}")
    else:
        run_app()
