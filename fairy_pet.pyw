"""夢境神明 像素桌寵 (pixel desktop pet with a care system).

Run:  pythonw fairy_pet.pyw          (no console window)
      python fairy_pet.pyw --sheet   (export spritesheet.png/.json + valley.png, e.g. for Unity)

Mouse: drag = pick her up, click = pat her, double-click = open her dream shrine panel, right-click = menu.
She walks on the desktop, climbs onto window frames and strolls along their tops.
Her needs (food / clean / mood / energy) drop over time and are saved between runs.
"""
import json
import math
import os
import random
import shutil
import sys
import time

from PIL import Image, ImageDraw

# ---------------------------------------------------------------- palette
T = (0, 0, 0, 0)
K = (50, 42, 66, 255)        # line colour (dark navy-plum)
W = (255, 255, 255, 255)     # white cloth
W2 = (238, 226, 244, 255)    # cloth shade
G = (190, 180, 206, 255)     # grey-lilac detail
LN = (150, 142, 170, 255)    # inner part lines
H = (250, 250, 252, 255)     # hair (white)
H2 = (218, 216, 230, 255)    # hair shade
H3 = (164, 146, 176, 255)    # hair deep shade
S = (255, 245, 245, 255)     # skin (very pale)
S2 = (246, 206, 204, 255)    # skin shade
E1 = (96, 90, 118, 255)      # iris rim (dark)
E2 = (240, 240, 248, 255)    # iris (white)
E3 = (196, 194, 214, 255)    # pupil (pale grey)
P = (255, 182, 200, 255)     # blush
GL = (206, 200, 222, 255)    # glasses
WI = (226, 240, 255, 96)     # wing (translucent)
WV = (170, 200, 240, 210)    # wing vein
FL = (206, 230, 170, 255)    # moonflower centre (pale green)
M = (214, 92, 110, 255)      # mouth inside
RED = (255, 110, 140, 255)   # heart
BLUE = (140, 196, 248, 255)
BALL = (255, 160, 190, 255)
WATER = (120, 180, 240, 255)
STARLIGHT = (255, 250, 220, 255)

# 無口對話庫（幾乎都是省略號，不連外網）
LINES = {
    "idle": ("……", "…………", "……嗯。", "……在。", "……。"),
    "pat": ("……", "……嗯。", "…………", "……♥", "……不要。"),
    "feed": ("……", "……甜。", "……糖。", "…………嗯。"),
    "bath": ("……", "……水。", "…………", "……好了。"),
    "play": ("……", "……接住了。", "…………", "……再一次。"),
    "sleep": ("……", "……Zzz", "…………", "……夢。"),
    "plant": ("……", "……種下了。", "…………"),
    "meteor": ("……", "……流星。", "…………", "……願。"),
    "hungry": ("……餓。", "……", "…………糖果。"),
    "dirty": ("……澡。", "……", "…………"),
    "bored": ("……無聊。", "……", "…………陪我。"),
    "tired": ("……睏。", "……", "…………想睡。"),
    "fly": ("……", "……飛。", "…………", "……風。"),
    "game": ("……", "…………", "……好。", "……開始。"),
    "chat": ("……", "…………", "……嗯。", "……在聽。", "……。",
             "……雪。", "……宮殿。", "……你。", "……慢慢。"),
}

CW, CH = 44, 50   # character canvas
OX, OY = 2, 12    # padding (room for bubbles / hearts)
FW, FH = CW + 2 * OX, CH + OY
FEET = OY + 49


# left half of the front sprite (mirrored to 36 px, placed at x+4).
# o line, c/d beret, h/s hair, k/q skin, w/x dress, e tights
ART_L = [
    "...........ooooooo",
    "........oooccccccc",
    "......oocccccccccc",
    ".....occcccccccccc",
    "....occccccccccccc",
    "...odccccccccccccc",
    "...oddcccccccccccc",
    "..oodddddddddddddd",
    "..ohhhhhhhhhhhhhhh",
    ".ohhhhhhshhhhhhhhh",
    ".ohhhhhshhhhhshhhh",
    "ohhhhhshhhhhshhhhh",
    "ohhhhshhhhhshhhhhh",
    "ohhhhshhhhshhhhhhh",
    "ohhhshhhhhhhhhhhhh",
    "ohhhshkhhkkhhkkhkh",
    "ohhhsskkkkkkkkkkkk",
    "ohhhsskkkkkkkkkkkk",
    "ohhhhskkkkkkkkkkkk",
    "ohhhhskkkkkkkkkkkk",
    "ohhhhskkkkkkkkkkkk",
    "ohhhhskkkkkkkkkkkk",
    "ohhhhskkkkkkkkkkkk",
    "ohhhhskkkkkkkkkkkk",
    "ohhhhhskkkkkkkkkkk",
    "ohhhhhsqkkkkkkkkkk",
    "ohhhhhhsqkkkkkkkkk",
    "ohhhhhhhsqqkkkkkkk",
    "ohhhhhhhhhssooqkkk",
    "ohhhhhhhhhhhhooxww",
    "ohhhhhhhhhhhowwxww",
    "ohhhhhhhhhhowwwwww",
    "ohhhhhhhowwwwowwww",
    "ohhhhhhhowwwwowwww",
    "ohhhhhhhowwwwowwww",
    "ohhhhhhhoxwwxowwww",
    "ohhhhhhhookkoowwww",
    "ohhhhhhh.oo.owwwww",
    "ohhhhhhh...owwwwww",
    ".ohhhhh...owwwwwww",
    ".ohhhho..owwwwwwww",
    "..oooo..owwwwwwwww",
    "........owxwwxwwxw",
    ".......owwwwwwwwww",
    ".......oxwxwxwxwxw",
    "........oxoxoxoxox",
    "............oeeo..",
    "............oeeo..",
    "...........owwwwo.",
    "...........oooooo.",
]
LN2 = (104, 94, 110, 255)
PAL = {"o": LN2, "c": (255, 255, 255, 255), "d": (232, 228, 238, 255), "h": (252, 250, 253, 255),
       "s": (226, 220, 232, 255), "k": (255, 246, 244, 255), "q": (246, 226, 228, 255),
       "w": (255, 255, 255, 255), "x": (232, 228, 238, 255), "e": (244, 242, 247, 255)}
EYE_OPEN = [".LLLLL.", "LiiiiiL", "riWWWir", "rWiiiWr", "riWWWir", ".riiir.", ".L.L.L."]


def art_base(legs="stand", view="front"):
    im = Image.new("RGBA", (CW, CH), T)
    pxl = im.load()
    for y, row in enumerate(ART_L):
        assert len(row) == 18, (y, row)
        for x, ch in enumerate(row + row[::-1]):
            if view == "back":
                if ch in "kq" or (ch == "h" and 8 <= y <= 15):
                    ch = "s" if (x + y) % 5 == 0 else "h"
                elif ch in "wx" and 28 <= y <= 40 and 9 <= x <= 26:
                    ch = "s" if (x + y) % 5 == 0 else "h"     # long hair down her back
            if ch in PAL:
                c = PAL[ch]
                if ch == "h" and 16 <= y <= 40 and (x in (6, 37)) and (y // 3) % 2 == 0:
                    c = PAL["s"]                       # wavy texture in the long hair
                pxl[x + 4, y] = c
    if legs != "stand":
        for y in range(46, 50):
            for x in range(13, 31):
                pxl[x, y] = T
        lx_l, lx_r, lift_l, lift_r = 16, 24, 0, 0
        if legs == "walk1":
            lx_l, lift_r = 15, 1
        elif legs == "walk2":
            lx_r, lift_l = 25, 1
        for lx, lift in ((lx_l, lift_l), (lx_r, lift_r)):
            for y in range(46 - lift, 48 - lift):
                pxl[lx, y] = LN2; pxl[lx + 3, y] = LN2
                pxl[lx + 1, y] = PAL["e"]; pxl[lx + 2, y] = PAL["e"]
            y = 48 - lift
            pxl[lx - 1, y] = LN2; pxl[lx + 4, y] = LN2
            for x in range(lx, lx + 4):
                pxl[x, y] = W
            for x in range(lx - 1, lx + 5):
                pxl[x, y + 1] = LN2
    return im


def outline(im):
    src = im.copy()
    sp, op = src.load(), im.load()
    for y in range(im.height):
        for x in range(im.width):
            if sp[x, y][3] != 0:
                continue
            nb = [sp[x + dx, y + dy] for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))
                  if 0 <= x + dx < im.width and 0 <= y + dy < im.height and sp[x + dx, y + dy][3] != 0]
            if nb:
                op[x, y] = WV if all(n[3] < 255 for n in nb) else LN2
    return im


def draw_eye(px, ex, ey, kind, right):
    """Her eye: round pale iris with a white ring, thick top lash with a flick, spiky lower lashes."""
    cmap = {"L": (92, 82, 96, 255), "r": (176, 166, 178, 255), "i": (224, 218, 226, 255), "W": W}
    rows = [r[::-1] for r in EYE_OPEN] if right else EYE_OPEN
    flick = ex + 7 if right else ex - 1
    if kind == "open":
        for j, row in enumerate(rows):
            for i, ch in enumerate(row):
                if ch in cmap:
                    px(ex + i, ey + j, cmap[ch])
        px(flick, ey + 1, cmap["L"]); px(flick + (1 if right else -1), ey, cmap["L"])
    elif kind == "closed":
        for i in range(7):
            px(ex + i, ey + 4, cmap["L"])
        for i in (1, 3, 5):
            px(ex + i, ey + 5, cmap["L"])
        px(flick, ey + 3, cmap["L"])
    elif kind == "happy":
        for i, dy in enumerate((5, 4, 3, 3, 3, 4, 5)):
            px(ex + i, ey + dy, cmap["L"])
    elif kind == "surprise":
        for i, j in ((2, 1), (3, 1), (4, 1), (1, 2), (5, 2), (1, 3), (5, 3), (1, 4), (5, 4), (2, 5), (3, 5), (4, 5)):
            px(ex + i, ey + j, cmap["r"])
        for i in (2, 3, 4):
            for j in (2, 3, 4):
                px(ex + i, ey + j, cmap["i"])
        px(ex + 3, ey + 3, W)
    elif kind == "sad":
        for j, row in enumerate(rows[3:]):
            for i, ch in enumerate(row):
                if ch in cmap:
                    px(ex + i, ey + 3 + j, cmap[ch])
        for i in range(7):
            px(ex + i, ey + 2 + ((6 - i) // 4 if right else i // 4), cmap["L"])


def frame(eyes="open", mouth="w", wing=0, legs="stand", arms="down", fx=None, turn=0, view=None):
    view = view or ("q3" if turn else "front")
    if view == "q3":
        turn = 2
    im = Image.new("RGBA", (CW, CH), T)
    d = ImageDraw.Draw(im)
    for mirror in (False, True):                             # translucent wings (behind)
        f = (lambda x: CW - 1 - x) if mirror else (lambda x: x)
        up = [(11, 31), (1, 22 + wing), (0, 27 + wing), (2, 33 + wing), (10, 35)]
        lo = [(11, 35), (2, 38 + wing), (2, 42 + wing), (7, 43 + wing), (11, 38)]
        for poly in (up, lo):
            pts = [(f(x), y) for x, y in poly]
            d.polygon(pts, fill=WI, outline=WV)
            d.line([pts[0], pts[2]], fill=WV)
    if view == "back":                                       # seen from behind, wings sit in front
        back = Image.new("RGBA", (CW, CH), T)
        back.alpha_composite(art_base(legs, "back"))
        im = back
        d = ImageDraw.Draw(im)
    else:
        im.alpha_composite(art_base(legs))
        d = ImageDraw.Draw(im)
    px = lambda x, y, c: d.point((x, y), fill=c)
    HH, HS = PAL["h"], PAL["s"]

    braid_x = (7, CW - 10) if view in ("front", "q3", "back") else (12,)
    for x0 in braid_x:                                       # braids, bows at top and end, tassels
        for y in range(29, 45):
            k = (y - 29) // 2
            a, b = (HH, HS) if k % 2 == 0 else (HS, HH)
            px(x0, y, a); px(x0 + 1, y, b); px(x0 + 2, y, a)
            px(x0 - 1, y, LN2); px(x0 + 3, y, LN2)
        for by in (29, 44):
            d.polygon([(x0 + 1, by), (x0 - 2, by - 2), (x0 - 2, by + 2)], fill=W, outline=LN2)
            d.polygon([(x0 + 1, by), (x0 + 4, by - 2), (x0 + 4, by + 2)], fill=W, outline=LN2)
        for y in range(46, 50):
            px(x0, y, HH); px(x0 + 1, y, HS); px(x0 + 2, y, HH)

    if view == "side":                                       # profile facing right
        skin = PAL["k"]
        for y in range(15, 29):                               # back of the head covers the left of the face
            for x in range(8, 20):
                if im.getpixel((x, y)) in (skin, PAL["q"]):
                    px(x, y, HS if (x + y) % 5 == 0 else HH)
        d.polygon([(17, 18), (13, 15), (13, 21)], fill=W, outline=LN2)      # ribbon by the ear
        for y in range(21, 28):
            px(14, y, W); px(15, y, (232, 228, 238, 255))
        for ox, oy in ((0, -1), (1, -1), (-1, 0), (2, 0), (-1, 1), (2, 1), (0, 2), (1, 2)):
            px(28 + ox, 17 + oy, (176, 166, 178, 255))
        draw_eye(px, 26, 19, eyes, True)
        for i in range(4):
            px(28 + i, 26, (255, 226, 230, 255))
        LIP = (214, 156, 166, 255)
        mcx = 31
        if mouth == "open":
            d.rectangle([mcx, 27, mcx + 1, 28], fill=M)
        elif mouth in ("smile",):
            px(mcx, 28, LIP); px(mcx + 1, 27, LIP)
        else:
            px(mcx, 27, LIP)
        px(34, 22, (246, 226, 228, 255))                       # nose tip shade on the cheek line
    elif view in ("front", "q3"):
        t = turn
        for rx_, sgn in ((7, -1), (36, 1)):                      # white ribbons hanging by the face
            if t and sgn < 0:
                continue
            d.polygon([(rx_, 17), (rx_ + 3 * sgn, 15), (rx_ + 3 * sgn, 19)], fill=W, outline=LN2)
            for y in range(19, 27):
                px(rx_ + sgn, y, W); px(rx_ + 2 * sgn, y, (232, 228, 238, 255))

        for cxd in (19 + t, 24 + t):                             # two round dot brows
            for ox, oy in ((0, -1), (1, -1), (-1, 0), (2, 0), (-1, 1), (2, 1), (0, 2), (1, 2)):
                px(cxd + ox, 17 + oy, (176, 166, 178, 255))
        lx, rx, ey = 13 + t, 24 + t - (1 if t else 0), 19
        draw_eye(px, lx, ey, eyes, False)
        draw_eye(px, rx, ey, eyes, True)
        for bx in (lx + 1, rx + 1):                              # faint blush
            for i in range(5):
                px(bx + i, ey + 7, (255, 226, 230, 255))
        cx = 21 + t                                              # tiny dot mouth
        LIP = (214, 156, 166, 255)
        if mouth == "w":
            px(cx, 27, LIP); px(cx + 1, 27, LIP)
        elif mouth == "open":
            d.rectangle([cx, 27, cx + 1, 28], fill=M)
        elif mouth == "smile":
            px(cx - 1, 27, LIP); px(cx, 28, LIP); px(cx + 1, 28, LIP); px(cx + 2, 27, LIP)
        elif mouth == "o":
            px(cx, 27, M); px(cx + 1, 27, M); px(cx, 28, M); px(cx + 1, 28, M)

    if view in ("front", "q3"):
        for x, y in ((20, 30), (20, 31), (21, 31), (22, 31), (23, 30), (23, 31)):   # black collar bow
            px(x + turn, y, (52, 46, 56, 255))
    if view == "back":                                       # translucent wings over her back
        wl = Image.new("RGBA", (CW, CH), T)
        wd = ImageDraw.Draw(wl)
        for mirror in (False, True):
            f = (lambda x: CW - 1 - x) if mirror else (lambda x: x)
            for poly in ([(20, 31), (5, 22 + wing), (3, 27 + wing), (6, 33 + wing), (19, 35)],
                         [(20, 35), (7, 38 + wing), (7, 42 + wing), (12, 43 + wing), (20, 38)]):
                pts = [(f(x), y) for x, y in poly]
                wd.polygon(pts, fill=(226, 240, 255, 120), outline=WV)
                wd.line([pts[0], pts[2]], fill=WV)
        im.alpha_composite(wl)
        d = ImageDraw.Draw(im)
        px = lambda x, y, c: d.point((x, y), fill=c)
    if arms == "up":
        for hx in (10, 32):
            d.rectangle([hx, 27, hx + 1, 28], fill=PAL["k"])
    outline(im)

    out = Image.new("RGBA", (FW, FH), T)
    out.alpha_composite(im, (OX, OY))
    od = ImageDraw.Draw(out)
    heart = ((0, 0), (1, 0), (3, 0), (4, 0), (0, 1), (1, 1), (2, 1), (3, 1), (4, 1), (1, 2), (2, 2), (3, 2), (2, 3))
    if fx == "heart":
        for hx, hy in ((4, 6), (40, 2)):
            for x, y in heart:
                od.point((hx + x, hy + y), fill=RED)
    elif fx in ("z1", "z2"):
        zx, zy = (36, 6) if fx == "z1" else (40, 1)
        for x, y in ((0, 0), (1, 0), (2, 0), (2, 1), (1, 2), (0, 3), (0, 4), (1, 4), (2, 4)):
            od.point((zx + x, zy + y), fill=LN2)
    return out


def side_frame(phase=0, wing=0, kneel=False, blink=False):
    """Profile facing right. phase 0..3 = walk cycle."""
    if kneel:
        return frame(eyes="closed" if blink else "happy", mouth="w", wing=0, view="q3")
    fr = frame(eyes="closed" if blink else "open", mouth="w", wing=wing,
               legs=("stand", "walk1", "stand", "walk2")[phase % 4], view="side")
    if phase % 2 == 1:
        moved = Image.new("RGBA", fr.size, T)
        moved.paste(fr, (0, -1))
        fr = moved
    return fr


def six_views():
    """Front, 3/4 right, right, back, left, 3/4 left (for the reference sheet)."""
    front = frame(view="front")
    q3 = frame(view="q3")
    side = frame(view="side")
    back = frame(view="back")
    flip = lambda im: im.transpose(Image.FLIP_LEFT_RIGHT)
    return [("正面", front), ("右前", q3), ("右側", side), ("背面", back), ("左側", flip(side)), ("左前", flip(q3))]


# ---- a moonflower (Ipomoea alba) that grows on the desktop:
#      stage 0 seedling, 1 vine with a twisted bud, 2 open bloom, 3 bloom glowing at night
FLW, FLH = 28, 40
LEAF, LEAF2, VINE = (120, 178, 120, 255), (88, 146, 100, 255), (150, 160, 110, 255)
PETAL, PETAL2, STAR = (255, 255, 255, 255), (236, 240, 236, 255), (206, 230, 170, 255)


def heart_leaf(d, x, y, flip=False):
    pts = [(0, 0), (1, 0), (3, 0), (4, 0), (0, 1), (1, 1), (2, 1), (3, 1), (4, 1), (1, 2), (2, 2), (3, 2), (2, 3)]
    for dx, dy in pts:
        d.point((x + (4 - dx if flip else dx), y + dy), fill=LEAF)
    d.point((x + 2, y + 1), fill=LEAF2); d.point((x + 2, y + 2), fill=LEAF2)


def flower_frame(stage, glow=0):
    im = Image.new("RGBA", (FLW, FLH), T)
    d = ImageDraw.Draw(im)
    cx = FLW // 2
    top = (28, 18, 16, 16)[stage]
    for y in range(top, FLH - 1):
        d.point((cx + (1 if (y // 3) % 2 else 0), y), fill=VINE)
    heart_leaf(d, cx - 6, 30)
    heart_leaf(d, cx + 1, 28, flip=True)
    if stage >= 1:
        heart_leaf(d, cx - 7, 22)
        heart_leaf(d, cx + 2, 20, flip=True)
    if stage == 1:
        for i, (dx, dy) in enumerate(((0, 0), (0, -1), (1, -2), (0, -3), (0, -4), (1, -5), (0, -6))):
            d.point((cx + dx, top - 1 + dy), fill=PETAL if i % 2 else PETAL2)
        d.point((cx + 1, top - 3), fill=STAR)
    if stage >= 2:
        fy = top - 4
        if stage == 3:
            g = Image.new("RGBA", (FLW, FLH), T)
            ImageDraw.Draw(g).ellipse([cx - 10, fy - 10, cx + 10, fy + 10], fill=(220, 238, 255, 60 + 50 * glow))
            im.alpha_composite(g)
            d = ImageDraw.Draw(im)
        d.ellipse([cx - 7, fy - 7, cx + 7, fy + 7], fill=PETAL)
        for ang in range(5):
            a_ = math.radians(ang * 72 - 90 + 36)
            d.point((round(cx + 7 * math.cos(a_)), round(fy + 7 * math.sin(a_))), fill=PETAL2)
        for ang in range(5):
            a_ = math.radians(ang * 72 - 90)
            for r in range(1, 7):
                d.point((round(cx + r * math.cos(a_)), round(fy + r * math.sin(a_))), fill=STAR)
        d.point((cx, fy), fill=(240, 236, 160, 255))
        for dx, dy in ((-3, -3), (3, -2), (-2, 3), (4, 1), (-4, 0)):
            d.point((cx + dx, fy + dy), fill=PETAL2)
    src = im.copy()
    sp, op = src.load(), im.load()
    for y in range(FLH):
        for x in range(FLW):
            if sp[x, y][3] != 0:
                continue
            n = [sp[x + a, y + b] for a, b in ((1, 0), (-1, 0), (0, 1), (0, -1))
                 if 0 <= x + a < FLW and 0 <= y + b < FLH and sp[x + a, y + b][3] == 255]
            if n:
                r, g_, b_ = [sum(c[i] for c in n) / len(n) for i in range(3)]
                op[x, y] = (int(r * 0.6 + 20), int(g_ * 0.6 + 24), int(b_ * 0.6 + 34), 255)
    return im


def deco(im, kind, t=0):
    im = im.copy()
    d = ImageDraw.Draw(im)
    pt = lambda x, y, c: d.point((x + OX, y + OY), fill=c)
    if kind == "food":        # 白色包裝糖（扭糖紙）
        # 中間糖身
        for x, y in ((35, 22), (36, 22), (37, 22), (34, 23), (35, 23), (36, 23), (37, 23), (38, 23),
                     (34, 24), (35, 24), (36, 24), (37, 24), (38, 24), (35, 25), (36, 25), (37, 25)):
            pt(x, y, W)
        # 細線與高光
        pt(36, 23, (236, 236, 244, 255)); pt(36, 24, LN2)
        # 兩側扭結糖紙
        for x, y in ((32, 23), (33, 22), (33, 24), (31, 23)):
            pt(x, y, W)
        for x, y in ((39, 22), (40, 23), (39, 24), (41, 23)):
            pt(x, y, W)
        pt(33, 23, (220, 220, 230, 255)); pt(39, 23, (220, 220, 230, 255))
        if t:   # 咬一口／掉屑
            pt(24, 29, W); pt(25, 28, W); pt(26, 29, (236, 236, 244, 255))
    elif kind == "bubbles":
        spots = [(3, 24), (40, 18), (4, 40), (40, 38), (22, 0)] if t == 0 else [(5, 18), (41, 26), (2, 34), (38, 44), (16, 1)]
        for x, y in spots:
            d.ellipse([x + OX - 2, y + OY - 2, x + OX + 1, y + OY + 1], outline=BLUE)
            pt(x - 1, y - 1, W)
    elif kind == "ball":
        by = -11 if t == 0 else -6
        d.ellipse([19 + OX, by + OY, 24 + OX, by + 5 + OY], fill=BALL, outline=LN2)
        pt(20, by + 1, W)
    elif kind == "sweat":
        pt(35, 14, BLUE); pt(35, 15, BLUE); pt(36, 15, BLUE)
    elif kind == "water":
        can = [(34, 18), (35, 18), (36, 18), (37, 18), (33, 19), (34, 19), (35, 19), (36, 19), (37, 19), (38, 19),
               (33, 20), (34, 20), (35, 20), (36, 20), (37, 20), (38, 20), (39, 19), (40, 18)]
        for x, y in can:
            pt(x, y - t, (210, 214, 222, 255))
        pt(34, 18 - t, LN2); pt(38, 18 - t, LN2)
        drops = [(38, 22), (40, 26), (39, 30)] if t == 0 else [(39, 24), (41, 28), (38, 32)]
        for x, y in drops:
            pt(x, y, WATER); pt(x, y + 1, BLUE)
    elif kind.startswith("need_"):
        layer = Image.new("RGBA", im.size, T)
        d = ImageDraw.Draw(layer)
        d.rectangle([29, 0, 40, 8], fill=W, outline=K)
        d.point((31, 9), fill=K); d.point((32, 9), fill=K); d.point((31, 10), fill=K)
        icon = kind[5:]
        pts = {
            "food": ([(33, 3), (34, 3), (35, 3), (36, 3), (32, 4), (33, 4), (34, 4), (35, 4), (36, 4), (37, 4),
                      (33, 5), (34, 5), (35, 5), (36, 5), (31, 4), (38, 4)], W,
                     [(34, 4), (35, 4)], LN2),
            "bath": ([(34, 2), (34, 3), (33, 4), (34, 4), (35, 4), (33, 5), (34, 5), (35, 5), (34, 6)], BLUE, [], K),
            "play": ([(32, 3), (33, 3), (35, 3), (36, 3), (32, 4), (33, 4), (34, 4), (35, 4), (36, 4),
                      (33, 5), (34, 5), (35, 5), (34, 6)], RED, [], K),
            "sleep": ([(32, 2), (33, 2), (34, 2), (34, 3), (33, 4), (32, 5), (32, 6), (33, 6), (34, 6),
                       (36, 5), (37, 5), (36, 6), (37, 6)], K, [], K),
        }[icon]
        for p in pts[0]:
            d.point(p, fill=pts[1])
        for p in pts[2]:
            d.point(p, fill=pts[3])
        im.alpha_composite(layer, (4, 0))
    return im


def app_dir():
    """安裝／執行目錄（exe 旁邊；開發時為腳本目錄）。"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def resource_dir():
    """打包進 exe 的資源目錄（PyInstaller 的 _MEIPASS）。"""
    if getattr(sys, "frozen", False):
        return getattr(sys, "_MEIPASS", app_dir())
    return os.path.dirname(os.path.abspath(__file__))


BASE_FILE = os.path.join(resource_dir(), "chibi_base.png")


SIDE_FACE = {                                     # hand-drawn profile face, x30..43 (rows 18..29)
    18: "3444444442" + "0...",
    19: "3441111144" + "0...",
    20: "3443666344" + "0...",
    21: "3443666344" + "0...",
    22: "3444666444" + "40..",
    23: "3444111444" + "0...",
    24: "3444444444" + "0...",
    25: "3445544444" + "0...",
    26: "3445544412" + "0...",
    27: "3444444420" + "....",
    28: "334444420." + "....",
    29: "33444200.." + "....",
}
HAIR_FILL = ["34433443344334", "43344334433443"]
SPRITE_PAL = {"0": (96, 86, 100), "1": (160, 150, 164), "2": (190, 182, 194), "3": (214, 208, 218),
              "4": (232, 228, 236), "5": (250, 226, 230), "6": (246, 244, 248), "7": (255, 255, 255)}


def side_base():
    """Right-facing profile drawn in the same pixels/palette as her front sprite."""
    base = Image.open(BASE_FILE).convert("RGBA")
    src = base.copy()
    sp, pp = src.load(), base.load()
    for y, face in SIDE_FACE.items():
        for x in range(16, 30):                          # back of the head: her own hair pixels
            pp[x, y] = sp[31 + (x - 16) % 8, y]
        for i, ch in enumerate(face):                    # hand-drawn profile face, x30..43
            x = 30 + i
            pp[x, y] = (0, 0, 0, 0) if ch == "." else SPRITE_PAL[ch] + (255,)
    return base


def draw_legs(base, lift_l=0, lift_r=0):
    """Two separate legs (white tights, white shoes) with a gap between them."""
    pp = base.load()
    O, SH, WH, LT = (96, 86, 100, 255), (214, 208, 218, 255), (255, 255, 255, 255), (246, 244, 248, 255)
    for y in range(44, CH):
        for x in range(13, 31):
            pp[x, y] = (0, 0, 0, 0)
    for x0, lift in ((16, lift_l), (23, lift_r)):
        top, bottom = 44, CH - 1 - lift
        for y in range(top, bottom - 1):                    # tights
            pp[x0, y] = O; pp[x0 + 4, y] = O
            pp[x0 + 1, y] = SH; pp[x0 + 2, y] = WH; pp[x0 + 3, y] = LT
        y = bottom - 1                                      # shoe
        pp[x0 - 1, y] = O; pp[x0 + 5 if x0 > 20 else x0 + 4, y] = O
        for x in range(x0, x0 + (5 if x0 > 20 else 4)):
            pp[x, y] = WH
        for x in range(x0 - 1, x0 + (6 if x0 > 20 else 5)):
            pp[x, bottom] = O


def paint_wings(out, phase=0, side=False):
    """半透明感的白色翅膀（實心淡白，適配透明色鍵）。"""
    layer = Image.new("RGBA", out.size, T)
    d = ImageDraw.Draw(layer)
    flap = phase % 2
    w1, w2, vein = (244, 250, 255, 210), (220, 236, 252, 170), (190, 214, 240, 200)
    if side:
        # 側面：翅膀在背後（左側）
        up = [(14, 28 + OY), (2, 18 + OY - flap), (0, 26 + OY), (4, 34 + OY + flap), (13, 33 + OY)]
        lo = [(14, 33 + OY), (3, 36 + OY), (2, 42 + OY + flap), (8, 43 + OY), (13, 36 + OY)]
        for poly in (up, lo):
            d.polygon(poly, fill=w1)
            d.line([poly[0], poly[2]], fill=vein)
    else:
        for mirror in (False, True):
            f = (lambda x: FW - 1 - x) if mirror else (lambda x: x)
            up = [(13, 28 + OY), (1, 18 + OY - flap), (0, 26 + OY), (3, 34 + OY + flap), (12, 33 + OY)]
            lo = [(13, 33 + OY), (2, 36 + OY), (2, 42 + OY + flap), (8, 43 + OY), (12, 36 + OY)]
            for poly in (up, lo):
                pts = [(f(x), y) for x, y in poly]
                d.polygon(pts, fill=w1 if not flap else w2)
                d.line([pts[0], pts[2]], fill=vein)
    out.alpha_composite(layer)
    return out


def from_base(eyes="open", bob=0, sway=0, fx=None, flip=False, side=False, wing=0):
    """Her sprite exactly as drawn, plus wings / overlays and offsets."""
    base = side_base() if side else Image.open(BASE_FILE).convert("RGBA")
    draw_legs(base)
    if eyes != "open":
        pxl = base.load()
        LID, LINE = (214, 208, 218, 255), (160, 150, 164, 255)
        eye_ranges = ((30, 36),) if side else ((14, 19), (24, 30))
        for x0, x1 in eye_ranges:
            for x in range(x0, x1 + 1):
                for y in range(23, 27):
                    if 0 <= x < CW and pxl[x, y][3]:
                        pxl[x, y] = LID
            if eyes == "closed":
                for x in range(x0, x1 + 1):
                    if 0 <= x < CW:
                        pxl[x, 25] = LINE
            elif eyes == "happy":
                w = x1 - x0
                for i in range(w + 1):
                    yy = 26 - min(i, w - i) // 1 if min(i, w - i) < 2 else 24
                    if 0 <= x0 + i < CW:
                        pxl[x0 + i, int(yy)] = LINE
    draw_legs(base, lift_l=1 if sway > 0 else 0, lift_r=1 if sway < 0 else 0)
    if flip:
        base = base.transpose(Image.FLIP_LEFT_RIGHT)
    out = Image.new("RGBA", (FW, FH), T)
    # 翅膀在身後（哥德裝也保留淡白夢翼）
    paint_wings(out, phase=wing, side=side)
    out.alpha_composite(base, (OX, OY + bob))
    od = ImageDraw.Draw(out)
    heart = ((0, 0), (1, 0), (3, 0), (4, 0), (0, 1), (1, 1), (2, 1), (3, 1), (4, 1), (1, 2), (2, 2), (3, 2), (2, 3))
    if fx == "heart":
        for hx, hy in ((4, 4), (40, 1)):
            for x, y in heart:
                od.point((hx + x, hy + y), fill=RED)
    elif fx in ("z1", "z2"):
        zx, zy = (38, 5) if fx == "z1" else (41, 1)
        for x, y in ((0, 0), (1, 0), (2, 0), (2, 1), (1, 2), (0, 3), (0, 4), (1, 4), (2, 4)):
            od.point((zx + x, zy + y), fill=(96, 86, 100, 255))
    return out


def lie_frame(phase=0):
    """側躺睡覺：把立繪旋轉後放在畫布底部，加上枕頭與 Zzz。"""
    base = Image.open(BASE_FILE).convert("RGBA")
    pxl = base.load()
    lid, line = (214, 208, 218, 255), (160, 150, 164, 255)
    for x0, x1 in ((14, 19), (24, 30)):
        for x in range(x0, x1 + 1):
            for y in range(23, 27):
                if pxl[x, y][3]:
                    pxl[x, y] = lid
        for x in range(x0, x1 + 1):
            pxl[x, 25] = line
    rot = base.rotate(90, expand=True, resample=Image.NEAREST)
    out = Image.new("RGBA", (FW, FH), T)
    od = ImageDraw.Draw(out)
    pillow = [(6, FH - 14), (7, FH - 15), (8, FH - 15), (9, FH - 15), (10, FH - 15), (11, FH - 15),
              (12, FH - 15), (13, FH - 14), (6, FH - 13), (7, FH - 13), (8, FH - 13), (9, FH - 13),
              (10, FH - 13), (11, FH - 13), (12, FH - 13), (13, FH - 13)]
    for x, y in pillow:
        od.point((x, y), fill=W)
    for x in range(6, 14):
        od.point((x, FH - 12), fill=(232, 228, 238, 255))
    rx = max(0, (FW - rot.width) // 2)
    ry = FH - rot.height
    out.alpha_composite(rot, (rx, ry + (1 if phase else 0)))
    od = ImageDraw.Draw(out)
    zx, zy = (FW - 12, 8) if phase == 0 else (FW - 9, 3)
    for x, y in ((0, 0), (1, 0), (2, 0), (2, 1), (1, 2), (0, 3), (0, 4), (1, 4), (2, 4)):
        od.point((zx + x, zy + y), fill=(96, 86, 100, 255))
    return out


def build_frames():
    f = {}
    for w in (0, 1):
        idle = from_base(bob=0, wing=w)
        f[f"idle{w}"] = from_base(bob=w, wing=w)
        f[f"blink{w}"] = from_base(bob=w, wing=w)
        f[f"walk{w}"] = from_base(bob=-w, sway=1 if w else -1, wing=w)
        f[f"happy{w}"] = from_base(bob=-2 * w, fx="heart", wing=w)
        f[f"carry{w}"] = from_base(bob=0, sway=w, wing=w)
        f[f"sleep{w}"] = lie_frame(w)
        f[f"smile{w}"] = from_base(bob=w, wing=w)
        f[f"eat{w}"] = deco(from_base(bob=w, wing=w), "food", w)
        f[f"bath{w}"] = deco(from_base(bob=w, wing=w), "bubbles", w)
        f[f"play{w}"] = deco(from_base(bob=-2 * w, wing=w), "ball", w)
        f[f"sad{w}"] = deco(from_base(wing=w), "sweat")
        f[f"climb{w}"] = from_base(bob=-w, sway=1 if w else -1, wing=w)
        f[f"fly{w}"] = from_base(bob=-2 - w, wing=w)
        f[f"water{w}"] = deco(from_base(bob=w, sway=1 if w else 0, wing=w), "water", w)
        for need in ("food", "bath", "play", "sleep"):
            f[f"need_{need}{w}"] = deco(idle, "need_" + need)
        f[f"plant{w}"] = from_base(bob=1, wing=w)
    for p in range(4):
        f[f"side{p}"] = from_base(bob=-(p % 2), sway=(0, 1, 0, -1)[p], wing=p % 2)
    f["turn0"] = from_base(wing=0)
    return f


# ---------------------------------------------------------------- moonflower valley / snowing white palace
def valley(fr, w=180, h=100, t=0):
    """舊版月光花谷（匯出與相容用）。"""
    return dream_house(fr, w, h, t)


def _palace_tower(d, x, y, tw, th, spire=14, warm=False):
    """一座積雪白塔：塔身、雪檐、尖頂。"""
    wall, shade, snow, line = (248, 248, 252, 255), (228, 228, 238, 255), (255, 255, 255, 255), (186, 186, 204, 255)
    d.rectangle([x, y, x + tw, y + th], fill=wall)
    d.rectangle([x + tw - 3, y, x + tw, y + th], fill=shade)
    # snowy battlement / eaves
    d.rectangle([x - 2, y + 6, x + tw + 2, y + 9], fill=snow)
    d.line([(x - 2, y + 9), (x + tw + 2, y + 9)], fill=line)
    # windows
    for wy in (y + 14, y + 28, y + 42):
        if wy + 8 >= y + th - 4:
            break
        wx = x + tw // 2 - 2
        fill = (255, 236, 190, 255) if warm else (186, 210, 240, 255)
        d.rectangle([wx, wy, wx + 4, wy + 6], fill=fill)
        d.point((wx + 1, wy + 1), fill=(255, 255, 240, 255))
    # spire
    tip = [(x + tw // 2, y - spire), (x - 1, y + 7), (x + tw + 1, y + 7)]
    d.polygon(tip, fill=snow)
    d.line([tip[0], tip[1]], fill=line)
    d.line([tip[0], tip[2]], fill=line)
    d.point((x + tw // 2, y - spire), fill=(255, 250, 230, 255))


def dream_house(fr, w=220, h=120, t=0, meteor=None):
    """下雪的白色宮殿：夜空、多座雪塔、暖窗、飄雪，可疊流星。"""
    rnd = random.Random(11)
    im = Image.new("RGBA", (w, h), (0, 0, 0, 255))
    d = ImageDraw.Draw(im)
    top, bot = (28, 34, 72), (150, 162, 198)
    for y in range(h):
        k = y / h
        d.line([(0, y), (w, y)], fill=tuple(int(a + (b - a) * k) for a, b in zip(top, bot)) + (255,))
    for _ in range(55):
        x, y = rnd.randrange(w), rnd.randrange(int(h * 0.50))
        tw = (x * 7 + y * 3 + t) % 10
        d.point((x, y), fill=STARLIGHT if tw else (190, 198, 230, 255))
    # soft moon
    d.ellipse([w - 48, 4, w - 22, 30], fill=(255, 250, 235, 55))
    d.ellipse([w - 44, 8, w - 26, 26], fill=(255, 252, 240, 255))
    d.ellipse([w - 40, 10, w - 30, 20], fill=(236, 236, 228, 255))
    d.ellipse([w - 42, 10, w - 28, 24], fill=(255, 252, 240, 255))
    # snow ground
    ground_y = int(h * 0.78)
    d.polygon([(0, ground_y + 6), (w, ground_y + 2), (w, h), (0, h)], fill=(214, 220, 236, 255))
    d.polygon([(0, ground_y), (w, ground_y - 4), (w, ground_y + 8), (0, ground_y + 10)], fill=(242, 246, 252, 255))
    for i in range(0, w, 3):
        d.point((i, ground_y - 1 + (i // 7) % 2), fill=(255, 255, 255, 255))
    # distant snow hills
    for base, col in ((0.62, (170, 184, 214)), (0.70, (198, 208, 228))):
        ph = rnd.random() * 4
        pts = [(x, int(h * base + 4 * math.sin(x / 28 + ph))) for x in range(0, w + 1, 4)]
        d.polygon(pts + [(w, ground_y + 2), (0, ground_y + 2)], fill=col + (255,))

    # ---- palace silhouette (back to front)
    wall, shade, snow, line = (250, 250, 254, 255), (230, 232, 242, 255), (255, 255, 255, 255), (180, 184, 204, 255)
    # main keep
    hx, hy, hw, hh = w // 2 - 42, ground_y - 48, 84, 50
    d.rectangle([hx, hy + 10, hx + hw, hy + hh], fill=wall)
    d.rectangle([hx + hw - 4, hy + 10, hx + hw, hy + hh], fill=shade)
    # snow roof ridge over keep
    roof = [(hx - 4, hy + 14), (hx + hw // 2, hy - 8), (hx + hw + 4, hy + 14)]
    d.polygon(roof, fill=snow)
    d.line([roof[0], roof[1], roof[2]], fill=line)
    d.rectangle([hx - 3, hy + 12, hx + hw + 3, hy + 16], fill=snow)
    # grand door
    door_x = hx + hw // 2
    d.rectangle([door_x - 7, hy + 28, door_x + 7, hy + hh], fill=(196, 178, 160, 255))
    d.arc([door_x - 7, hy + 20, door_x + 7, hy + 36], 180, 0, fill=(196, 178, 160, 255))
    d.rectangle([door_x - 6, hy + 28, door_x + 6, hy + hh - 1], fill=(170, 150, 132, 255))
    d.point((door_x + 3, hy + 40), fill=(255, 236, 180, 255))
    # warm arched windows on keep
    for wx in (hx + 10, hx + 22, hx + hw - 28, hx + hw - 16):
        d.rectangle([wx, hy + 22, wx + 6, hy + 34], fill=(255, 236, 190, 255))
        d.arc([wx, hy + 18, wx + 6, hy + 26], 180, 0, fill=(255, 236, 190, 255))
        glow = Image.new("RGBA", (14, 18), (0, 0, 0, 0))
        ImageDraw.Draw(glow).ellipse([0, 0, 13, 17], fill=(255, 236, 180, 45))
        im.alpha_composite(glow, (wx - 4, hy + 16))
        d = ImageDraw.Draw(im)
    # side towers
    _palace_tower(d, hx - 22, ground_y - 62, 18, 64, spire=16, warm=True)
    _palace_tower(d, hx + hw + 4, ground_y - 58, 16, 60, spire=14, warm=True)
    # center tall spire
    _palace_tower(d, door_x - 8, ground_y - 78, 16, 40, spire=20, warm=False)
    # balcony snow rail
    d.rectangle([hx + 18, hy + 18, hx + hw - 18, hy + 20], fill=snow)
    for bx in range(hx + 20, hx + hw - 18, 6):
        d.point((bx, hy + 17), fill=line)
    # moonflowers in snow (small white blooms)
    for i in range(14):
        x = rnd.randrange(6, w - 6)
        y = rnd.randrange(ground_y - 1, h - 3)
        r = 2 if rnd.random() < 0.6 else 3
        d.ellipse([x - r, y - r, x + r, y + r], fill=(252, 253, 255, 255))
        d.point((x, y), fill=(206, 230, 170, 255))
        d.line([(x, y + r), (x, min(h - 1, y + r + 2))], fill=(120, 150, 120, 255))
    # falling snow (animated by t)
    snow_rnd = random.Random(3)
    for i in range(70):
        sx = (snow_rnd.randrange(w) + t * (1 + i % 3)) % w
        sy = (snow_rnd.randrange(h) + t * (1 + (i % 2))) % h
        size = 1 + (i % 3 == 0)
        col = (255, 255, 255, 220) if i % 4 else (230, 238, 255, 180)
        if size == 1:
            d.point((int(sx), int(sy)), fill=col)
        else:
            d.point((int(sx), int(sy)), fill=col)
            d.point((int(sx) + 1, int(sy)), fill=col)
            d.point((int(sx), int(sy) + 1), fill=(255, 255, 255, 140))
    # meteor streak
    if meteor is not None:
        mx, my, age = meteor
        for i in range(10):
            a = max(0, 200 - i * 18)
            d.point((int(mx - i * 2), int(my + i * 0.6)), fill=(255, 250, 230, a))
        d.point((int(mx), int(my)), fill=(255, 255, 255, 255))
        d.point((int(mx) + 1, int(my)), fill=(255, 240, 200, 220))
    if fr is not None:
        fr2 = fr.resize((FW * 2 // 3, FH * 2 // 3), Image.NEAREST) if fr.width > 20 else fr
        im.alpha_composite(fr2, (door_x - fr2.width // 2, hy + hh - fr2.height + 2))
    return im


def meteor_sprite(frame=0):
    """桌面流星小圖。"""
    im = Image.new("RGBA", (28, 12), T)
    d = ImageDraw.Draw(im)
    for i in range(12):
        a = max(0, 220 - i * 16)
        d.point((20 - i * 2 + (frame % 2), 4 + i // 4), fill=(255, 250, 230, a))
    d.ellipse([20, 2, 25, 7], fill=STARLIGHT)
    d.point((22, 3), fill=W)
    return im


def export_sheet(frames, folder):
    names = list(frames)
    cols = 8
    rows = (len(names) + cols - 1) // cols
    sheet = Image.new("RGBA", (cols * FW, rows * FH), T)
    meta = {"frameWidth": FW, "frameHeight": FH, "pixelsPerUnit": FH, "pivot": [0.5, (FH - FEET) / FH], "frames": {}}
    for i, n in enumerate(names):
        x, y = (i % cols) * FW, (i // cols) * FH
        sheet.alpha_composite(frames[n], (x, y))
        meta["frames"][n] = {"x": x, "y": y, "w": FW, "h": FH}
    sheet.save(os.path.join(folder, "spritesheet.png"))
    with open(os.path.join(folder, "spritesheet.json"), "w", encoding="utf-8") as fp:
        json.dump(meta, fp, indent=1)
    dream_house(None).save(os.path.join(folder, "valley.png"))
    return sheet


# ---------------------------------------------------------------- autostart (Windows Startup folder)
def _startup_vbs_path():
    return os.path.join(
        os.environ.get("APPDATA", os.path.expanduser("~")),
        r"Microsoft\Windows\Start Menu\Programs\Startup",
        "夢境神明桌寵.vbs",
    )


def autostart_enabled():
    return os.path.isfile(_startup_vbs_path())


def set_autostart(on):
    path = _startup_vbs_path()
    if not on:
        try:
            os.remove(path)
        except OSError:
            pass
        return True
    here = app_dir()
    if getattr(sys, "frozen", False):
        target = sys.executable
        run = f'sh.Run """{target}""", 0, False\n'
    else:
        pyw = os.path.join(here, "fairy_pet.pyw")
        pythonw = shutil.which("pythonw") or "pythonw"
        run = f'sh.Run """{pythonw}"" ""{pyw}""", 0, False\n'
    body = (
        'Option Explicit\n'
        f'Dim sh: Set sh = CreateObject("WScript.Shell")\n'
        f'sh.CurrentDirectory = "{here}"\n'
        + run
    )
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fp:
            fp.write(body)
        return True
    except OSError:
        return False


def pick_line(kind):
    return random.choice(LINES.get(kind, LINES["idle"]))


# ---------------------------------------------------------------- pixel font (Cubic 11 / 俐方體11號)
PIXEL_FONT_FILE = os.path.join(resource_dir(), "fonts", "Cubic_11.ttf")
PIXEL_FONT_FAMILY = "俐方體11號"
_FONT_LOADED = False


def load_pixel_font():
    """把專案內的像素字型私有載入給本行程使用（不寫入系統字型資料夾）。"""
    global _FONT_LOADED
    if _FONT_LOADED:
        return PIXEL_FONT_FAMILY
    if not os.path.isfile(PIXEL_FONT_FILE):
        return "Microsoft JhengHei UI"
    try:
        import ctypes
        FR_PRIVATE = 0x10
        if ctypes.windll.gdi32.AddFontResourceExW(PIXEL_FONT_FILE, FR_PRIVATE, 0) > 0:
            _FONT_LOADED = True
            return PIXEL_FONT_FAMILY
    except Exception:
        pass
    return "Microsoft JhengHei UI"


# ---------------------------------------------------------------- care stats (saved between runs)
STATS = [("food", "飽食"), ("clean", "清潔"), ("joy", "心情"), ("energy", "體力")]
DECAY = {"food": 1.2, "clean": 0.6, "joy": 0.9, "energy": 0.5}   # points per minute while awake


class Care:
    def __init__(self, path):
        self.path = path
        self.v = {k: 80.0 for k, _ in STATS}
        self.born = time.time()
        try:
            with open(path, encoding="utf-8") as fp:
                data = json.load(fp)
            self.v.update({k: float(data["stats"][k]) for k, _ in STATS if k in data.get("stats", {})})
            self.born = data.get("born", self.born)
            away = min(max(0.0, time.time() - data.get("last", time.time())) / 60, 600)
            self.tick(away, asleep=False, offline=True)
        except Exception:
            pass

    def clamp(self):
        for k in self.v:
            self.v[k] = max(0.0, min(100.0, self.v[k]))

    def tick(self, minutes, asleep, offline=False):
        rate = 0.35 if offline else 1.0
        for k, _ in STATS:
            if k == "energy" and asleep:
                self.v[k] += 6 * minutes
            else:
                self.v[k] -= DECAY[k] * minutes * rate
        if self.v["food"] < 20 or self.v["clean"] < 20:
            self.v["joy"] -= 0.5 * minutes
        self.clamp()

    def add(self, **kw):
        for k, dv in kw.items():
            self.v[k] += dv
        self.clamp()

    def need(self):
        low = min(self.v, key=lambda k: self.v[k])
        if self.v[low] >= 30:
            return None
        return {"food": "food", "clean": "bath", "joy": "play", "energy": "sleep"}[low]

    def save(self):
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            with open(self.path, "w", encoding="utf-8") as fp:
                json.dump({"stats": self.v, "born": self.born, "last": time.time()}, fp)
        except Exception:
            pass


# ---------------------------------------------------------------- desktop windows (platforms)
def list_windows(own):
    import ctypes
    from ctypes import wintypes
    u = ctypes.windll.user32
    dwm = ctypes.windll.dwmapi
    out = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(h, _):
        if h in own or not u.IsWindowVisible(h) or u.IsIconic(h) or u.GetWindowTextLengthW(h) == 0:
            return True
        cloaked = ctypes.c_int(0)
        dwm.DwmGetWindowAttribute(h, 14, ctypes.byref(cloaked), 4)
        if cloaked.value:
            return True
        r = wintypes.RECT()
        if dwm.DwmGetWindowAttribute(h, 9, ctypes.byref(r), ctypes.sizeof(r)) != 0:
            u.GetWindowRect(h, ctypes.byref(r))
        if r.right - r.left > 160 and r.bottom - r.top > 60:
            out.append((h, r.left, r.top, r.right, r.bottom))
        return True

    u.EnumWindows(cb, 0)
    return out


# ---------------------------------------------------------------- desktop pet
def run_pet(frames):
    import ctypes
    import tkinter as tk
    import tkinter.font as tkfont
    from PIL import ImageTk

    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass
    KEY = "#ff00fe"
    try:  # 工作列用自己的圖示
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("DreamGod.FairyPet")
    except Exception:
        pass
    root = tk.Tk()
    try:  # 所有視窗的圖示都換成月光花
        _icon = tk.PhotoImage(master=root, file=os.path.join(resource_dir(), "assets", "icons", "moonflower_64.png"))
        root.iconphoto(True, _icon)
        root._moonflower_icon = _icon
    except Exception:
        pass
    root.overrideredirect(True)
    root.attributes("-topmost", True)
    root.configure(bg=KEY)
    root.attributes("-transparentcolor", KEY)
    label = tk.Label(root, bg=KEY, bd=0, highlightthickness=0, cursor="hand2")
    label.pack()
    try:
        dpi = ctypes.windll.user32.GetDpiForSystem() / 96
    except Exception:
        dpi = 1.0

    family = load_pixel_font()
    # 像素字以接近原生 11px 的倍數較清晰
    px = max(11, int(round(11 * dpi)))
    font_sm = tkfont.Font(family=family, size=max(9, px - 2))
    font_ui = tkfont.Font(family=family, size=px)
    font_bd = tkfont.Font(family=family, size=px + 2)
    root.option_add("*Font", font_ui)
    root.option_add("*Menu.font", font_ui)
    root.option_add("*Button.font", font_ui)
    root.option_add("*Label.font", font_ui)
    root.option_add("*Entry.font", font_ui)
    root.option_add("*Text.font", font_sm)

    class RECT(ctypes.Structure):
        _fields_ = [("l", ctypes.c_long), ("t", ctypes.c_long), ("r", ctypes.c_long), ("b", ctypes.c_long)]
    rr_ = RECT()
    ctypes.windll.user32.SystemParametersInfoW(0x30, 0, ctypes.byref(rr_), 0)
    area = (rr_.l, rr_.t, rr_.r, rr_.b)

    care = Care(os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "FairyPet", "save.json"))
    st = {"scale": max(2, round(2 * dpi)), "fx": area[0] + (area[2] - area[0]) * 0.75, "fy": float(area[3]),
          "dir": 1, "mode": "idle", "timer": 40, "tick": 0, "blink": 0, "lonely": 0, "walk": True,
          "drag": None, "moved": False, "vy": 0.0, "target": None, "wins": [], "own": set(), "name": "idle0",
          "bubble": None, "bubble_ttl": 0, "meteors": [], "panel_meteor": None, "chat_log": []}
    cache = {}
    mcache = {}

    def img(name):
        key = (name, st["scale"], st["dir"])
        if key not in cache:
            im = frames[name]
            if st["dir"] < 0:
                im = im.transpose(Image.FLIP_LEFT_RIGHT)
            im = im.resize((FW * st["scale"], FH * st["scale"]), Image.NEAREST)
            bg = Image.new("RGB", im.size, (255, 0, 254))
            bg.paste(im.convert("RGB"), (0, 0), im.getchannel("A").point(lambda v: 255 if v >= 40 else 0))
            cache[key] = ImageTk.PhotoImage(bg)
        return cache[key]

    half = lambda: FW * st["scale"] / 2
    garden = []          # each: {"x": screen x, "born": time, "win": Toplevel, "lbl": Label, "key": cache key}
    fcache = {}
    garden_path = os.path.join(os.path.dirname(care.path), "garden.json")

    def fimg(stage, glow):
        key = (stage, glow, st["scale"])
        if key not in fcache:
            im = flower_frame(stage, glow).resize((FLW * st["scale"], FLH * st["scale"]), Image.NEAREST)
            bg = Image.new("RGB", im.size, (255, 0, 254))
            bg.paste(im.convert("RGB"), (0, 0), im.getchannel("A").point(lambda v: 255 if v >= 100 else 0))
            fcache[key] = ImageTk.PhotoImage(bg)
        return fcache[key]

    def save_garden():
        try:
            with open(garden_path, "w", encoding="utf-8") as fp:
                json.dump([{"x": g["x"], "born": g["born"]} for g in garden], fp)
        except Exception:
            pass

    def plant_flower(x, born=None):
        x = max(area[0] + 10, min(area[2] - 40, x))
        fw = tk.Toplevel(root)
        fw.overrideredirect(True)
        fw.attributes("-topmost", True)
        fw.configure(bg=KEY)
        fw.attributes("-transparentcolor", KEY)
        lb = tk.Label(fw, bg=KEY, bd=0, highlightthickness=0, cursor="hand2")
        lb.pack()
        g = {"x": x, "born": born or time.time(), "win": fw, "lbl": lb, "key": None}

        def pick(e, g=g):
            if flower_stage(g) >= 2:
                care.add(joy=8)
                set_mode("happy", 24)
            garden.remove(g); g["win"].destroy(); save_garden()
        lb.bind("<Button-1>", pick)
        garden.append(g)
        update_flower(g)
        save_garden()

    def flower_stage(g):
        age = time.time() - g["born"]          # sprout -> bud (1 min) -> bloom (3 min) -> glowing (6 min)
        return 0 if age < 60 else 1 if age < 180 else 2 if age < 360 else 3

    def update_flower(g):
        stg = flower_stage(g)
        glow = (st["tick"] // 15) % 2 if stg == 3 else 0
        key = (stg, glow, st["scale"])
        if g["key"] != key:
            g["lbl"].configure(image=fimg(stg, glow))
            g["key"] = key
        g["win"].geometry(f"+{int(g['x'])}+{int(area[3] - FLH * st['scale'])}")

    try:
        with open(garden_path, encoding="utf-8") as fp:
            saved_garden = json.load(fp)
    except Exception:
        saved_garden = []

    def platforms():
        ps = [(None, area[0], area[3], area[2])]
        for h, l, t, r, b in st["wins"]:
            if t > area[1] + 20:
                ps.append((h, l + 6, t, r - 6))
        return ps

    def win_rect(h):
        return next((w for w in st["wins"] if w[0] == h), None)

    def set_mode(m, t):
        st["mode"], st["timer"] = m, t

    def say(kind, ttl=70, text=None):
        """在她頭上冒出一句話。"""
        text = text if text is not None else pick_line(kind)
        st["bubble_ttl"] = ttl
        bw = tk.Toplevel(root)
        bw.overrideredirect(True)
        bw.attributes("-topmost", True)
        bw.configure(bg="#fff8fc")
        tk.Label(bw, text=text, bg="#fff8fc", fg="#4a3c4e",
                 font=font_sm, padx=8, pady=4).pack()
        if st["bubble"] is not None:
            try:
                st["bubble"].destroy()
            except Exception:
                pass
        st["bubble"] = bw
        place_bubble()
        return text

    def place_bubble():
        bw = st["bubble"]
        if bw is None:
            return
        try:
            if not bw.winfo_exists():
                st["bubble"] = None
                return
            bw.update_idletasks()
            bx = int(st["fx"] - bw.winfo_reqwidth() / 2)
            by = int(st["fy"] - FEET * st["scale"] - bw.winfo_reqheight() - 8)
            bw.geometry(f"+{bx}+{by}")
        except Exception:
            pass

    def mimg(frame):
        key = (frame, st["scale"])
        if key not in mcache:
            im = meteor_sprite(frame).resize((28 * st["scale"], 12 * st["scale"]), Image.NEAREST)
            bg = Image.new("RGB", im.size, (255, 0, 254))
            bg.paste(im.convert("RGB"), (0, 0), im.getchannel("A").point(lambda v: 255 if v >= 40 else 0))
            mcache[key] = ImageTk.PhotoImage(bg)
        return mcache[key]

    def spawn_meteor():
        if len(st["meteors"]) >= 3:
            return
        y = random.randint(area[1] + 40, max(area[1] + 80, area[3] - 220))
        x = float(area[0] - 20)
        mw = tk.Toplevel(root)
        mw.overrideredirect(True)
        mw.attributes("-topmost", True)
        mw.configure(bg=KEY)
        mw.attributes("-transparentcolor", KEY)
        lb = tk.Label(mw, bg=KEY, bd=0, highlightthickness=0, cursor="hand2")
        lb.pack()
        meta = {"x": x, "y": y, "win": mw, "lbl": lb, "age": 0, "vx": 3.2 * st["scale"]}

        def catch(_e, m=meta):
            care.add(joy=6)
            say("meteor", 50)
            try:
                st["meteors"].remove(m)
                m["win"].destroy()
            except Exception:
                pass
            set_mode("happy", 24)
            care.save()

        lb.bind("<Button-1>", catch)
        st["meteors"].append(meta)
        st["panel_meteor"] = (40, 20, 0)

    def refresh_windows():
        try:
            st["wins"] = list_windows(st["own"])
        except Exception:
            st["wins"] = []

    def support():
        best = None
        for p in platforms():
            h, l, t, r = p
            if l <= st["fx"] <= r and abs(t - st["fy"]) <= 4:
                if best is None or t < best[2]:
                    best = p
        return best

    def nearest_flower():
        if not garden:
            return None
        return min(garden, key=lambda g: abs(g["x"] - st["fx"]))

    def choose_next():
        n = care.need()
        if care.v["energy"] < 12:
            set_mode("sleep", 10 ** 9); say("tired", 60); return
        if n and random.random() < 0.5:
            set_mode("need", random.randint(40, 80)); return
        roll = random.random()
        # 更常去爬視窗
        if st["walk"] and roll < 0.42:
            p = support()
            cands = []
            for h, l, t, r, b in st["wins"]:
                if area[1] + 20 < t < st["fy"] - 40 and b >= st["fy"] - 20:
                    for side_x, face in ((l - 2, 1), (r + 2, -1)):
                        if p and p[1] - 8 <= side_x <= p[3] + 8:
                            cands.append((h, side_x, face))
            if cands:
                st["target"] = random.choice(cands)
                set_mode("goto", 900); return
        p0 = support()
        if roll > 0.78 and roll <= 0.88 and p0:
            st["dir"] = random.choice((-1, 1))
            set_mode("fly", random.randint(80, 160)); say("fly", 40); return
        if roll > 0.90 and p0 and p0[0] is None and care.v["joy"] > 40 and len(garden) < 14:
            set_mode("plant", 50); return
        if st["walk"] and roll < 0.72:
            st["dir"] = random.choice((-1, 1)); st["turning"] = 6; set_mode("walk", random.randint(60, 180))
        elif roll < 0.85:
            set_mode("smile", random.randint(25, 50))
        else:
            set_mode("idle", random.randint(40, 100))

    def step():
        try:
            tick()
        finally:
            root.after(50, step)

    def tick():
        st["tick"] += 1
        n_ = st["tick"]
        wing = (n_ // 4) % 2
        s = st["scale"]
        if n_ % 6 == 0:
            refresh_windows()
            for g in garden:
                update_flower(g)
        if n_ % 20 == 0:
            care.tick(1 / 60, asleep=st["mode"] == "sleep")
            if st["mode"] == "sleep" and care.v["energy"] >= 100 and st["lonely"] < 1800:
                set_mode("smile", 40)
        if n_ % 600 == 0:
            care.save()
        # 偶爾流星劃過桌面
        if n_ % 80 == 0 and random.random() < 0.18:
            spawn_meteor()
        alive = []
        for m in st["meteors"]:
            m["age"] += 1
            m["x"] += m["vx"]
            m["y"] += 0.55 * s
            try:
                m["lbl"].configure(image=mimg(m["age"] // 2))
                m["win"].geometry(f"+{int(m['x'])}+{int(m['y'])}")
            except Exception:
                continue
            if m["x"] < area[2] + 40 and m["y"] < area[3]:
                alive.append(m)
            else:
                try:
                    m["win"].destroy()
                except Exception:
                    pass
        st["meteors"] = alive
        if st["panel_meteor"] is not None:
            mx, my, age = st["panel_meteor"]
            st["panel_meteor"] = (mx + 3.5, my + 1.1, age + 1)
            if age > 40:
                st["panel_meteor"] = None
        if st["bubble_ttl"] > 0:
            st["bubble_ttl"] -= 1
            place_bubble()
            if st["bubble_ttl"] <= 0 and st["bubble"] is not None:
                try:
                    st["bubble"].destroy()
                except Exception:
                    pass
                st["bubble"] = None
        st["timer"] -= 1
        st["lonely"] += 1
        mode = st["mode"]

        if st["drag"] is not None:
            mode = "carry"
        elif mode == "climb":
            h, side_x, face = st["target"]
            w = win_rect(h)
            if not w:
                st["target"] = None; set_mode("idle", 20)
            else:
                st["fx"] = side_x - face * half() * 0.45
                st["fy"] -= 1.0 * s
                if st["fy"] <= w[2]:
                    st["fy"] = float(w[2]); st["fx"] = side_x + face * half() * 0.8
                    st["dir"] = face; st["target"] = None
                    set_mode("walk", random.randint(50, 120))
        elif mode == "fly":
            # 離地緩緩飛，側面撲翅
            hover = 18 * s + 4 * s * math.sin(n_ / 10)
            base_y = float(area[3])
            sup = support()
            if sup:
                base_y = float(sup[2])
            st["fy"] = base_y - hover
            st["fx"] += st["dir"] * 0.18 * s
            if st["fx"] < area[0] + 20 or st["fx"] > area[2] - 20:
                st["dir"] *= -1
            if st["timer"] <= 0:
                set_mode("idle", 30)
        else:
            sup = support()
            if sup is None:
                st["vy"] = min(st["vy"] + 0.45 * s, 5 * s)
                ny = st["fy"] + st["vy"]
                land = None
                for h, l, t, r in platforms():
                    if l <= st["fx"] <= r and st["fy"] - 1 <= t <= ny + 1:
                        land = t if land is None else min(land, t)
                if land is not None:
                    st["fy"], st["vy"] = float(land), 0.0
                    if mode in ("carry", "climb", "goto", "fly"):
                        set_mode("idle", 30)
                else:
                    st["fy"] = min(ny, float(area[3]))
                mode = "carry"
            else:
                st["vy"] = 0.0
                h, l, t, r = sup
                st["fy"] = float(t)          # ride along when the window moves vertically
                if st["lonely"] > 2400 and mode in ("idle", "walk", "smile", "need"):
                    set_mode("sleep", 10 ** 9); say("sleep", 50)
                elif st["timer"] <= 0 and mode != "sleep":
                    if mode == "plant":
                        plant_flower(st["fx"] + st["dir"] * half() * 0.5)
                        say("plant", 50)
                        set_mode("smile", 30)
                    elif mode in ("eat", "bath", "play", "happy", "fly"):
                        set_mode("idle", 40)
                    else:
                        choose_next()
                mode = st["mode"]
                if mode == "walk":
                    st["fx"] += st["dir"] * 0.20 * s   # 走慢一點
                    if st["fx"] < l + 2 or st["fx"] > r - 2:
                        if h is not None and random.random() < 0.35:
                            pass
                        else:
                            st["fx"] = max(l + 2, min(r - 2, st["fx"])); st["dir"] *= -1
                elif mode == "goto":
                    tg = st["target"]
                    if not tg or not win_rect(tg[0]):
                        st["target"] = None; set_mode("idle", 20)
                    else:
                        dx = tg[1] - tg[2] * half() * 0.45 - st["fx"]
                        st["dir"] = 1 if dx > 0 else -1
                        if abs(dx) <= 0.5 * s:
                            st["dir"] = tg[2]; set_mode("climb", 10 ** 9)
                        else:
                            st["fx"] += st["dir"] * min(abs(dx), 0.32 * s)
                mode = st["mode"]

        if st["blink"] > 0:
            st["blink"] -= 1
        elif random.random() < 0.012:
            st["blink"] = 3
        if mode in ("walk", "goto"):
            name = f"walk{(n_ // 5) % 2}"
        elif mode == "plant":
            name = f"plant{1 if (n_ // 10) % 4 == 3 else 0}"
        elif mode == "climb":
            name = f"climb{(n_ // 5) % 2}"
        elif mode == "fly":
            name = f"fly{(n_ // 3) % 2}"
        elif mode == "sleep":
            name = f"sleep{(n_ // 20) % 2}"
        elif mode in ("happy", "carry", "smile", "eat", "bath", "play"):
            name = f"{mode}{(n_ // (6 if mode in ('eat', 'bath') else 4)) % 2}"
        elif mode == "need":
            nd = care.need()
            name = (f"sad{wing}" if (n_ // 30) % 3 == 2 else f"need_{nd}{wing}") if nd else f"idle{wing}"
        else:
            name = f"blink{wing}" if st["blink"] else f"idle{wing}"
        st["name"] = name
        bob = (n_ // 8) % 2 if mode in ("idle", "smile", "need") else 0
        if mode in ("happy", "play"):
            ph = n_ % 12
            bob = -min(ph, 12 - ph)
        if mode in ("sleep", "fly"):
            bob = 0
        label.configure(image=img(name))
        root.geometry(f"+{int(st['fx'] - half())}+{int(st['fy'] - FEET * s + bob * s)}")
        place_bubble()

    # ---- mouse
    def press(e):
        st["drag"] = (e.x_root - st["fx"], e.y_root - st["fy"])
        st["moved"] = False
        st["lonely"] = 0

    def motion(e):
        if st["drag"]:
            st["moved"] = True
            st["fx"] = e.x_root - st["drag"][0]
            st["fy"] = min(float(area[3]), e.y_root - st["drag"][1])
            st["target"] = None
            if st["mode"] in ("climb", "goto"):
                set_mode("idle", 20)

    def release(e):
        st["drag"] = None
        st["lonely"] = 0
        st["vy"] = 0.0
        if not st["moved"]:
            care.add(joy=3)
            set_mode("happy", 24)
            say("pat", 45)
        elif st["mode"] == "sleep":
            set_mode("idle", 40)

    # ---- care actions
    def act(kind):
        st["lonely"] = 0
        if st["mode"] == "climb":
            return
        if kind == "feed":
            if care.v["food"] >= 95:
                set_mode("smile", 30)
                say("feed", 40)
            else:
                care.add(food=35, joy=4); set_mode("eat", 60); say("feed", 50)
        elif kind == "bath":
            care.add(clean=100, joy=3); set_mode("bath", 70); say("bath", 50)
        elif kind == "play":
            if care.v["energy"] < 10:
                set_mode("need", 40); say("tired", 40)
            else:
                care.add(joy=30, energy=-10, food=-5); set_mode("play", 70); say("play", 50)
        elif kind == "sleep":
            # 立刻躺到工作列上睡，方便觀察側躺姿勢
            st["target"] = None
            st["vy"] = 0.0
            st["fy"] = float(area[3])
            set_mode("sleep", 10 ** 9); say("sleep", 55)
        elif kind == "fly":
            st["target"] = None
            set_mode("fly", 160); say("fly", 45)
        elif kind == "plant":
            if support() and support()[0] is None:
                set_mode("plant", 50)
            else:
                return
        elif kind == "meteor":
            spawn_meteor()
            say("meteor", 40)
        care.save()

    def reply_chat(user_text):
        """依關鍵字 / 狀態回一句話（離線劇本）。"""
        t = (user_text or "").strip()
        low = t.lower()
        if not t:
            return pick_line("chat")
        if any(k in t for k in ("睡", "睏", "休息", "晚安")):
            act("sleep"); return pick_line("sleep")
        if any(k in t for k in ("餓", "吃", "飯", "餵", "糖", "糖果")):
            act("feed"); return pick_line("feed")
        if any(k in t for k in ("澡", "洗", "髒")):
            act("bath"); return pick_line("bath")
        if any(k in t for k in ("玩", "球", "遊戲")):
            act("play"); return pick_line("play")
        if any(k in t for k in ("流星", "許願", "星星")):
            act("meteor"); return pick_line("meteor")
        if any(k in t for k in ("飛", "翅膀")):
            act("fly"); return pick_line("fly")
        if any(k in t for k in ("遊戲", "小遊戲")):
            return pick_line("game")
        if any(k in t for k in ("愛", "喜歡", "想你", "你好", "嗨", "hello", "hi")) or "hello" in low:
            care.add(joy=5); return random.choice(("……", "…………", "……嗯。", "……你。"))
        need = care.need()
        if need:
            return pick_line({"food": "hungry", "bath": "dirty", "play": "bored", "sleep": "tired"}[need])
        return pick_line("chat")

    def open_minigame_meteor():
        """限時接流星：點中桌面流星得分。"""
        say("game", 40)
        gw = tk.Toplevel(root)
        gw.title("接流星")
        gw.attributes("-topmost", True)
        gw.resizable(False, False)
        gw.configure(bg="#1a1a2e", padx=10, pady=10)
        score = {"n": 0, "left": 20, "run": False}
        info = tk.Label(gw, text="點流星　0 / 8　　剩 20 秒", bg="#1a1a2e", fg="#efeaf6", font=font_ui)
        info.pack(pady=4)
        tip = tk.Label(gw, text="……流星會從桌面飛過。", bg="#1a1a2e", fg="#b8b0c8", font=font_sm)
        tip.pack()

        def game_spawn():
            before = len(st["meteors"])
            spawn_meteor()
            if len(st["meteors"]) <= before:
                return
            m = st["meteors"][-1]

            def scored(_e, m=m):
                if not score["run"]:
                    return
                score["n"] += 1
                try:
                    if m in st["meteors"]:
                        st["meteors"].remove(m)
                    m["win"].destroy()
                except Exception:
                    pass
                set_mode("happy", 16)

            m["lbl"].bind("<Button-1>", scored)

        def tick_game():
            if not gw.winfo_exists() or not score["run"]:
                return
            score["left"] -= 1
            if score["n"] >= 8 or score["left"] <= 0:
                score["run"] = False
                if score["n"] >= 8:
                    care.add(joy=15); say("meteor", 50); tip.configure(text="……接住了。")
                else:
                    tip.configure(text="……下次。")
                info.configure(text=f"結束　{score['n']} 顆")
                care.save()
                return
            info.configure(text=f"點流星　{score['n']} / 8　　剩 {score['left']} 秒")
            if random.random() < 0.6:
                game_spawn()
            gw.after(1000, tick_game)

        def start():
            if score["run"]:
                return
            score.update(n=0, left=20, run=True)
            tip.configure(text="……")
            tick_game()

        tk.Button(gw, text="開始", font=font_ui, command=start).pack(pady=8)
        tk.Button(gw, text="關閉", font=font_sm, command=gw.destroy).pack()

    def open_minigame_snow():
        """點飄落的雪花，15 秒內愈多愈好。"""
        say("game", 40)
        gw = tk.Toplevel(root)
        gw.title("飄雪")
        gw.attributes("-topmost", True)
        gw.resizable(False, False)
        bgc = "#dfe6f2"
        gw.configure(bg=bgc, padx=8, pady=8)
        cv = tk.Canvas(gw, width=320, height=220, bg="#c8d2e6", highlightthickness=0)
        cv.pack()
        score = {"n": 0, "left": 15}
        info = tk.Label(gw, text="點雪花　0　　剩 15 秒", bg=bgc, fg="#4a3c4e", font=font_ui)
        info.pack(pady=4)
        flakes = []

        def add_flake():
            x = random.randint(10, 310)
            fid = cv.create_oval(x, -6, x + 8, 2, fill="#ffffff", outline="#eef4ff")
            flakes.append({"id": fid, "y": -6.0, "x": float(x), "vy": 1.2 + random.random()})

        def on_click(e):
            hit = cv.find_overlapping(e.x - 6, e.y - 6, e.x + 6, e.y + 6)
            for f in list(flakes):
                if f["id"] in hit:
                    cv.delete(f["id"])
                    flakes.remove(f)
                    score["n"] += 1
                    info.configure(text=f"點雪花　{score['n']}　　剩 {score['left']} 秒")
                    break

        cv.bind("<Button-1>", on_click)

        def loop():
            if not gw.winfo_exists():
                return
            if random.random() < 0.45:
                add_flake()
            for f in list(flakes):
                f["y"] += f["vy"]
                cv.coords(f["id"], f["x"], f["y"], f["x"] + 8, f["y"] + 8)
                if f["y"] > 220:
                    cv.delete(f["id"])
                    flakes.remove(f)
            gw.after(50, loop)

        def timer():
            if not gw.winfo_exists():
                return
            score["left"] -= 1
            info.configure(text=f"點雪花　{score['n']}　　剩 {score['left']} 秒")
            if score["left"] <= 0:
                care.add(joy=min(20, 4 + score["n"]))
                say("game", 40, text="……" if score["n"] < 8 else "……好多雪。")
                info.configure(text=f"結束　接住 {score['n']} 片")
                care.save()
                return
            gw.after(1000, timer)

        loop()
        timer()

    # ---- home panel: snow palace + chat
    panel = {"win": None}

    def open_panel():
        if panel["win"] is not None and panel["win"].winfo_exists():
            panel["win"].deiconify(); panel["win"].lift(); return
        pw = tk.Toplevel(root)
        pw.title("無夢之夢・雪白宮殿")
        pw.attributes("-topmost", True)
        pw.resizable(False, False)
        bgc = "#f4f0f8"
        pw.configure(bg=bgc, padx=12, pady=10)
        vs = max(2, round(2 * dpi))
        scene = tk.Label(pw, bd=0, bg=bgc)
        scene.grid(row=0, column=0, columnspan=3, pady=(0, 8))
        age = tk.Label(pw, bg=bgc, fg="#4a3c4e", font=font_bd)
        age.grid(row=1, column=0, columnspan=3, sticky="w", pady=(0, 6))
        bars = {}
        colors = {"food": "#f2a86a", "clean": "#7cb8f0", "joy": "#f58aa6", "energy": "#9fd27c"}
        for i, (k, lbl) in enumerate(STATS, start=2):
            tk.Label(pw, text=lbl, bg=bgc, fg="#4a3c4e", font=font_ui).grid(row=i, column=0, sticky="w")
            c = tk.Canvas(pw, width=230, height=14, bg="#ddd5e4", highlightthickness=0)
            c.grid(row=i, column=1, padx=8, pady=3)
            val = tk.Label(pw, bg=bgc, fg="#4a3c4e", font=font_ui, width=4, anchor="e")
            val.grid(row=i, column=2)
            bars[k] = (c, val, colors[k])
        row = tk.Frame(pw, bg=bgc)
        row.grid(row=7, column=0, columnspan=3, pady=(10, 0))
        for txt, kind in (("餵食", "feed"), ("洗澡", "bath"), ("玩耍", "play"), ("睡覺", "sleep"),
                          ("飛行", "fly"), ("流星", "meteor")):
            tk.Button(row, text=txt, font=font_ui, width=5, relief="groove", bg="#ffffff",
                      command=lambda k=kind: act(k)).pack(side="left", padx=3)
        games = tk.Frame(pw, bg=bgc)
        games.grid(row=8, column=0, columnspan=3, pady=(6, 0))
        tk.Button(games, text="小遊戲・接流星", font=font_ui, width=14, relief="groove", bg="#ffffff",
                  command=open_minigame_meteor).pack(side="left", padx=3)
        tk.Button(games, text="小遊戲・飄雪", font=font_ui, width=12, relief="groove", bg="#ffffff",
                  command=open_minigame_snow).pack(side="left", padx=3)
        chat_frame = tk.Frame(pw, bg=bgc)
        chat_frame.grid(row=9, column=0, columnspan=3, sticky="ew", pady=(12, 0))
        tk.Label(chat_frame, text="跟她說話", bg=bgc, fg="#4a3c4e", font=font_ui).pack(anchor="w")
        log = tk.Text(chat_frame, height=5, width=42, font=font_sm,
                      bg="#ffffff", fg="#4a3c4e", relief="solid", bd=1, wrap="word")
        log.pack(fill="x", pady=4)
        log.configure(state="disabled")
        entry_row = tk.Frame(chat_frame, bg=bgc)
        entry_row.pack(fill="x")
        entry = tk.Entry(entry_row, font=font_ui, bg="#ffffff", fg="#4a3c4e")
        entry.pack(side="left", fill="x", expand=True, padx=(0, 6))

        def append_chat(who, text):
            log.configure(state="normal")
            log.insert("end", f"{who}　{text}\n")
            log.see("end")
            log.configure(state="disabled")
            st["chat_log"].append((who, text))
            if len(st["chat_log"]) > 40:
                st["chat_log"] = st["chat_log"][-40:]

        for who, text in st["chat_log"][-8:]:
            append_chat(who, text)

        def send(_e=None):
            msg = entry.get().strip()
            if not msg:
                return
            entry.delete(0, "end")
            append_chat("你", msg)
            ans = reply_chat(msg)
            append_chat("她", ans)
            say("chat", 70, text=ans)

        tk.Button(entry_row, text="送出", font=font_ui, width=6, relief="groove", bg="#ffffff",
                  command=send).pack(side="left")
        entry.bind("<Return>", send)
        holder = {}

        def upd():
            if not pw.winfo_exists():
                return
            fr = frames.get(st["name"], frames["idle0"])
            met = st["panel_meteor"]
            sc = dream_house(fr, t=st["tick"] // 10, meteor=met).resize((220 * vs, 120 * vs), Image.NEAREST)
            holder["img"] = ImageTk.PhotoImage(sc)
            scene.configure(image=holder["img"])
            days = int((time.time() - care.born) // 86400) + 1
            mood = {"food": "肚子餓了…", "bath": "想洗澡…", "play": "好無聊…", "sleep": "好睏…"}.get(care.need(), "宮殿在下雪 ♪")
            age.configure(text=f"夢境神明　降臨第 {days} 天　{mood}")
            for k, (c, val, col) in bars.items():
                v = care.v[k]
                c.delete("all")
                c.create_rectangle(0, 0, 230 * v / 100, 14, fill=col if v >= 30 else "#e0605a", width=0)
                for x in range(23, 230, 23):
                    c.create_line(x, 0, x, 14, fill=bgc)
                val.configure(text=f"{int(v)}")
            pw.after(400, upd)
        upd()
        panel["win"] = pw

    menu = tk.Menu(root, tearoff=0, font=font_ui)
    menu.add_command(label="無夢之夢（雪白宮殿）", command=open_panel)
    menu.add_separator()
    for txt, kind in (("餵食", "feed"), ("洗澡", "bath"), ("玩耍", "play"), ("睡覺", "sleep"),
                      ("飛行", "fly"), ("種月光花", "plant"), ("召來流星", "meteor")):
        menu.add_command(label=txt, command=lambda k=kind: act(k))
    menu.add_separator()
    menu.add_command(label="小遊戲・接流星", command=open_minigame_meteor)
    menu.add_command(label="小遊戲・飄雪", command=open_minigame_snow)
    menu.add_separator()
    walk_var = tk.BooleanVar(value=True)

    def toggle_walk():
        st["walk"] = walk_var.get()
        if not st["walk"] and st["mode"] in ("walk", "goto", "climb"):
            set_mode("idle", 60)
    menu.add_checkbutton(label="自由散步、爬視窗", variable=walk_var, command=toggle_walk)
    auto_var = tk.BooleanVar(value=autostart_enabled())

    def toggle_autostart():
        ok = set_autostart(auto_var.get())
        if not ok:
            auto_var.set(autostart_enabled())
            say("idle", 40)
        else:
            say("chat", 45)
    menu.add_checkbutton(label="開機自動啟動", variable=auto_var, command=toggle_autostart)
    size = tk.Menu(menu, tearoff=0, font=font_ui)
    for sc, lb in ((max(1, round(1.5 * dpi)), "小"), (max(2, round(2 * dpi)), "中"), (max(3, round(3 * dpi)), "大")):
        size.add_command(label=lb, command=lambda sc=sc: (st.update(scale=sc), cache.clear(), fcache.clear(), mcache.clear()))
    menu.add_cascade(label="大小", menu=size)
    menu.add_separator()

    def quit_():
        care.save()
        for m in list(st["meteors"]):
            try:
                m["win"].destroy()
            except Exception:
                pass
        if st["bubble"] is not None:
            try:
                st["bubble"].destroy()
            except Exception:
                pass
        root.destroy()
    menu.add_command(label="讓她回家（關閉）", command=quit_)

    label.bind("<ButtonPress-1>", press)
    label.bind("<B1-Motion>", motion)
    label.bind("<ButtonRelease-1>", release)
    label.bind("<Double-Button-1>", lambda e: open_panel())
    label.bind("<Button-3>", lambda e: menu.tk_popup(e.x_root, e.y_root))
    root.update_idletasks()
    try:
        hid = root.winfo_id()
        st["own"] = {hid, ctypes.windll.user32.GetParent(hid), ctypes.windll.user32.GetAncestor(hid, 2)}
    except Exception:
        pass
    refresh_windows()
    for g in saved_garden[:14]:
        plant_flower(g.get("x", area[0] + 100), g.get("born"))
    step()
    root.mainloop()


if __name__ == "__main__":
    here = app_dir()
    frames = build_frames()
    if "--sheet" in sys.argv:
        export_sheet(frames, here)
        print("exported", os.path.join(here, "spritesheet.png"))
    else:
        run_pet(frames)
