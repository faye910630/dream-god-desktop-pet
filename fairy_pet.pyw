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
FLW, FLH = 19, 26
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
    cx = 9
    top = (20, 12, 10, 10)[stage]
    for y in range(top, FLH):
        d.point((cx + (1 if (y // 3) % 2 else 0), y), fill=VINE)
    heart_leaf(d, cx - 5, 20)
    heart_leaf(d, cx + 1, 18, flip=True)
    if stage >= 1:
        heart_leaf(d, cx - 5, 14)
        heart_leaf(d, cx + 2, 12, flip=True)
    if stage == 1:
        for i, (dx, dy) in enumerate(((0, 0), (0, -1), (1, -2), (0, -3), (0, -4), (1, -5), (0, -6))):
            d.point((cx + dx, top - 1 + dy), fill=PETAL if i % 2 else PETAL2)
        d.point((cx + 1, top - 3), fill=STAR)
    if stage >= 2:
        fy = top - 5
        if stage == 3:
            g = Image.new("RGBA", (FLW, FLH), T)
            ImageDraw.Draw(g).ellipse([cx - 9, fy - 9, cx + 9, fy + 9], fill=(220, 238, 255, 60 + 50 * glow))
            im.alpha_composite(g)
            d = ImageDraw.Draw(im)
        d.ellipse([cx - 6, fy - 6, cx + 6, fy + 6], fill=PETAL)
        for ang in range(5):
            a_ = math.radians(ang * 72 - 90 + 36)
            d.point((round(cx + 6 * math.cos(a_)), round(fy + 6 * math.sin(a_))), fill=PETAL2)
        for ang in range(5):
            a_ = math.radians(ang * 72 - 90)
            for r in range(1, 6):
                d.point((round(cx + r * math.cos(a_)), round(fy + r * math.sin(a_))), fill=STAR)
        d.point((cx, fy), fill=(240, 236, 160, 255))
        for dx, dy in ((-3, -3), (3, -2), (-2, 3)):
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
    if kind == "food":        # rice ball in her raised hand
        for x, y in ((36, 21), (35, 22), (36, 22), (37, 22), (34, 23), (35, 23), (36, 23), (37, 23), (38, 23),
                     (34, 24), (35, 24), (36, 24), (37, 24), (38, 24)):
            pt(x, y, W)
        for x in (35, 36, 37):
            pt(x, 25, LN2); pt(x, 24, LN2)
        if t:
            pt(24, 29, W); pt(26, 28, W)
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
    elif kind.startswith("need_"):
        layer = Image.new("RGBA", im.size, T)
        d = ImageDraw.Draw(layer)
        d.rectangle([29, 0, 40, 8], fill=W, outline=K)
        d.point((31, 9), fill=K); d.point((32, 9), fill=K); d.point((31, 10), fill=K)
        icon = kind[5:]
        pts = {
            "food": ([(34, 2), (33, 3), (34, 3), (35, 3), (32, 4), (33, 4), (34, 4), (35, 4), (36, 4)], G,
                     [(33, 5), (34, 5), (35, 5), (33, 6), (34, 6), (35, 6)], K),
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


BASE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chibi_base.png")


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


def from_base(eyes="open", bob=0, sway=0, fx=None, flip=False, side=False):
    """Her sprite exactly as drawn, plus small overlays (hearts, zzz) and offsets."""
    base = side_base() if side else Image.open(BASE_FILE).convert("RGBA")
    draw_legs(base)
    if eyes != "open":
        pxl = base.load()
        LID, LINE = (214, 208, 218, 255), (160, 150, 164, 255)
        for x0, x1 in ((14, 19), (24, 30)):                 # her two eyes in this sprite
            for x in range(x0, x1 + 1):
                for y in range(23, 27):
                    if pxl[x, y][3]:
                        pxl[x, y] = LID
            if eyes == "closed":
                for x in range(x0, x1 + 1):
                    pxl[x, 25] = LINE
            elif eyes == "happy":
                w = x1 - x0
                for i in range(w + 1):
                    pxl[x0 + i, 24 + abs(i - w / 2) // 2 if False else x0 + i, 0] if False else None
                for i in range(w + 1):
                    yy = 26 - min(i, w - i) // 1 if min(i, w - i) < 2 else 24
                    pxl[x0 + i, int(yy)] = LINE
    draw_legs(base, lift_l=1 if sway > 0 else 0, lift_r=1 if sway < 0 else 0)
    if flip:
        base = base.transpose(Image.FLIP_LEFT_RIGHT)
    out = Image.new("RGBA", (FW, FH), T)
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


def build_frames():
    f = {}
    for w in (0, 1):
        idle = from_base(bob=0)
        f[f"idle{w}"] = from_base(bob=w)
        f[f"blink{w}"] = from_base(bob=w)
        f[f"walk{w}"] = from_base(bob=-w, sway=1 if w else -1)
        f[f"happy{w}"] = from_base(bob=-2 * w, fx="heart")
        f[f"carry{w}"] = from_base(bob=0, sway=w)
        f[f"sleep{w}"] = from_base(fx="z1" if w == 0 else "z2")
        f[f"smile{w}"] = from_base(bob=w)
        f[f"eat{w}"] = deco(from_base(bob=w), "food", w)
        f[f"bath{w}"] = deco(from_base(bob=w), "bubbles", w)
        f[f"play{w}"] = deco(from_base(bob=-2 * w), "ball", w)
        f[f"sad{w}"] = deco(from_base(), "sweat")
        f[f"climb{w}"] = from_base(bob=-w, sway=1 if w else -1)
        for need in ("food", "bath", "play", "sleep"):
            f[f"need_{need}{w}"] = deco(idle, "need_" + need)
        f[f"plant{w}"] = from_base(bob=1)
    for p in range(4):
        f[f"side{p}"] = from_base(bob=-(p % 2), sway=(0, 1, 0, -1)[p])
    f["turn0"] = from_base()
    return f


# ---------------------------------------------------------------- moonflower valley (her home scene)
def valley(fr, w=180, h=100, t=0):
    rnd = random.Random(7)
    im = Image.new("RGBA", (w, h), (0, 0, 0, 255))
    d = ImageDraw.Draw(im)
    top, bot = (26, 28, 66), (88, 70, 130)
    for y in range(h):
        k = y / h
        d.line([(0, y), (w, y)], fill=tuple(int(a + (b - a) * k) for a, b in zip(top, bot)) + (255,))
    for _ in range(60):                                         # stars
        x, y = rnd.randrange(w), rnd.randrange(int(h * 0.55))
        tw = (x * 7 + y * 3 + t) % 9
        d.point((x, y), fill=(255, 255, 230, 255) if tw else (190, 190, 230, 255))
    d.ellipse([w - 40, 8, w - 22, 26], fill=(255, 250, 220, 255))   # moon + glow
    d.ellipse([w - 35, 9, w - 21, 23], fill=(232, 226, 210, 255))
    d.ellipse([w - 36, 10, w - 22, 24], fill=(255, 250, 220, 255))
    hills = [(0.50, (52, 60, 108)), (0.62, (44, 74, 104)), (0.74, (36, 84, 96))]
    for base, col in hills:
        ph = rnd.random() * 6
        pts = [(x, int(h * base + 6 * math.sin(x / 23 + ph) + 3 * math.sin(x / 9 + ph))) for x in range(0, w + 1, 2)]
        d.polygon(pts + [(w, h), (0, h)], fill=col + (255,))
    for _ in range(46):                                         # moonflowers on vines
        x = rnd.randrange(3, w - 3)
        y = rnd.randrange(int(h * 0.60), h - 3)
        big = rnd.random() < 0.35
        r = 3 if big else 2
        glow = Image.new("RGBA", (r * 4 + 1, r * 4 + 1), (0, 0, 0, 0))
        ImageDraw.Draw(glow).ellipse([0, 0, r * 4, r * 4], fill=(220, 240, 255, 46))
        im.alpha_composite(glow, (x - r * 2, y - r * 2))
        lx_ = x + (3 if rnd.random() < 0.5 else -6)              # a little heart leaf
        for dx, dy in ((0, 0), (1, 0), (3, 0), (4, 0), (0, 1), (1, 1), (2, 1), (3, 1), (4, 1), (1, 2), (2, 2), (3, 2), (2, 3)):
            d.point((lx_ + dx, y + 1 + dy), fill=(86, 150, 104, 255))
        d.line([(x, y + r), (x, min(h - 1, y + r + 4))], fill=(96, 140, 96, 255))
        d.ellipse([x - r, y - r, x + r, y + r], fill=(252, 253, 255, 255))
        if big:
            for ang in range(5):
                a_ = math.radians(ang * 72 - 90)
                for rr in (1, 2):
                    d.point((round(x + rr * math.cos(a_)), round(y + rr * math.sin(a_))), fill=(206, 230, 170, 255))
        d.point((x, y), fill=(206, 230, 170, 255))
    if fr is not None:                                          # the fairy standing in the valley
        im.alpha_composite(fr, (w // 2 - FW // 2, h - FH - 2))
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
    valley(None).save(os.path.join(folder, "valley.png"))
    return sheet


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
    from PIL import ImageTk

    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass
    KEY = "#ff00fe"
    root = tk.Tk()
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

    class RECT(ctypes.Structure):
        _fields_ = [("l", ctypes.c_long), ("t", ctypes.c_long), ("r", ctypes.c_long), ("b", ctypes.c_long)]
    rr_ = RECT()
    ctypes.windll.user32.SystemParametersInfoW(0x30, 0, ctypes.byref(rr_), 0)
    area = (rr_.l, rr_.t, rr_.r, rr_.b)

    care = Care(os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "FairyPet", "save.json"))
    st = {"scale": max(2, round(2 * dpi)), "fx": area[0] + (area[2] - area[0]) * 0.75, "fy": float(area[3]),
          "dir": 1, "mode": "idle", "timer": 40, "tick": 0, "blink": 0, "lonely": 0, "walk": True,
          "drag": None, "moved": False, "vy": 0.0, "target": None, "wins": [], "own": set(), "name": "idle0"}
    cache = {}

    def img(name):
        key = (name, st["scale"], st["dir"])
        if key not in cache:
            im = frames[name]
            if st["dir"] < 0:
                im = im.transpose(Image.FLIP_LEFT_RIGHT)
            im = im.resize((FW * st["scale"], FH * st["scale"]), Image.NEAREST)
            bg = Image.new("RGB", im.size, (255, 0, 254))
            bg.paste(im.convert("RGB"), (0, 0), im.getchannel("A").point(lambda v: 255 if v >= 100 else 0))
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

    def choose_next():
        n = care.need()
        if care.v["energy"] < 12:
            set_mode("sleep", 10 ** 9); return
        if n and random.random() < 0.5:
            set_mode("need", random.randint(40, 80)); return
        roll = random.random()
        if st["walk"] and roll < 0.3:
            p = support()
            cands = []
            for h, l, t, r, b in st["wins"]:
                if area[1] + 20 < t < st["fy"] - 60 and b >= st["fy"] - 14:
                    for side_x, face in ((l - 2, 1), (r + 2, -1)):
                        if p and p[1] <= side_x <= p[3]:
                            cands.append((h, side_x, face))
            if cands:
                st["target"] = random.choice(cands)
                set_mode("goto", 900); return
        p0 = support()
        if roll > 0.9 and p0 and p0[0] is None and care.v["joy"] > 40 and len(garden) < 14:
            set_mode("plant", 50); return
        if st["walk"] and roll < 0.7:
            st["dir"] = random.choice((-1, 1)); st["turning"] = 4; set_mode("walk", random.randint(40, 140))
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
                st["fy"] -= 1.4 * s
                if st["fy"] <= w[2]:
                    st["fy"] = float(w[2]); st["fx"] = side_x + face * half() * 0.8
                    st["dir"] = face; st["target"] = None
                    set_mode("walk", random.randint(30, 90))
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
                    if mode in ("carry", "climb", "goto"):
                        set_mode("idle", 30)
                else:
                    st["fy"] = min(ny, float(area[3]))
                mode = "carry"
            else:
                st["vy"] = 0.0
                h, l, t, r = sup
                st["fy"] = float(t)          # ride along when the window moves vertically
                if st["lonely"] > 2400 and mode in ("idle", "walk", "smile", "need"):
                    set_mode("sleep", 10 ** 9)
                elif st["timer"] <= 0 and mode != "sleep":
                    if mode == "plant":
                        plant_flower(st["fx"] + st["dir"] * half() * 0.5)
                        set_mode("smile", 30)
                    elif mode in ("eat", "bath", "play", "happy"):
                        set_mode("idle", 40)
                    else:
                        choose_next()
                mode = st["mode"]
                if mode == "walk":
                    st["fx"] += st["dir"] * 0.45 * s
                    if st["fx"] < l + 2 or st["fx"] > r - 2:
                        if h is not None and random.random() < 0.35:
                            pass             # hop off the window edge
                        else:
                            st["fx"] = max(l + 2, min(r - 2, st["fx"])); st["dir"] *= -1
                elif mode == "goto":
                    tg = st["target"]
                    if not tg or not win_rect(tg[0]):
                        st["target"] = None; set_mode("idle", 20)
                    else:
                        dx = tg[1] - tg[2] * half() * 0.45 - st["fx"]
                        st["dir"] = 1 if dx > 0 else -1
                        if abs(dx) <= 0.6 * s:
                            st["dir"] = tg[2]; set_mode("climb", 10 ** 9)
                        else:
                            st["fx"] += st["dir"] * min(abs(dx), 0.6 * s)
                mode = st["mode"]

        if st["blink"] > 0:
            st["blink"] -= 1
        elif random.random() < 0.012:
            st["blink"] = 3
        if mode in ("walk", "goto") and st.get("turning", 0) > 0:
            st["turning"] -= 1
            name = "turn0"
        elif mode in ("walk", "goto"):
            name = f"side{(n_ // 3) % 4}"
        elif mode == "plant":
            name = f"plant{1 if (n_ // 10) % 4 == 3 else 0}"
        elif mode == "climb":
            name = f"climb{(n_ // 4) % 2}"
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
        label.configure(image=img(name))
        root.geometry(f"+{int(st['fx'] - half())}+{int(st['fy'] - FEET * s + bob * s)}")

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
            else:
                care.add(food=35, joy=4); set_mode("eat", 60)
        elif kind == "bath":
            care.add(clean=100, joy=3); set_mode("bath", 70)
        elif kind == "play":
            if care.v["energy"] < 10:
                set_mode("need", 40)
            else:
                care.add(joy=30, energy=-10, food=-5); set_mode("play", 70)
        elif kind == "sleep":
            set_mode("sleep", 10 ** 9)
        elif kind == "plant":
            if support() and support()[0] is None:
                set_mode("plant", 50)
            else:
                return
        care.save()

    # ---- home panel with the moonflower valley
    panel = {"win": None}

    def open_panel():
        if panel["win"] is not None and panel["win"].winfo_exists():
            panel["win"].deiconify(); panel["win"].lift(); return
        pw = tk.Toplevel(root)
        pw.title("無夢之夢・月光花谷")
        pw.attributes("-topmost", True)
        pw.resizable(False, False)
        bgc = "#efeaf6"
        pw.configure(bg=bgc, padx=12, pady=10)
        font = ("Microsoft JhengHei UI", 10)
        vs = max(2, round(2 * dpi))
        scene = tk.Label(pw, bd=0, bg=bgc)
        scene.grid(row=0, column=0, columnspan=3, pady=(0, 8))
        age = tk.Label(pw, bg=bgc, fg="#4a3c4e", font=("Microsoft JhengHei UI", 10, "bold"))
        age.grid(row=1, column=0, columnspan=3, sticky="w", pady=(0, 6))
        bars = {}
        colors = {"food": "#f2a86a", "clean": "#7cb8f0", "joy": "#f58aa6", "energy": "#9fd27c"}
        for i, (k, lbl) in enumerate(STATS, start=2):
            tk.Label(pw, text=lbl, bg=bgc, fg="#4a3c4e", font=font).grid(row=i, column=0, sticky="w")
            c = tk.Canvas(pw, width=230, height=14, bg="#ddd5e4", highlightthickness=0)
            c.grid(row=i, column=1, padx=8, pady=3)
            val = tk.Label(pw, bg=bgc, fg="#4a3c4e", font=font, width=4, anchor="e")
            val.grid(row=i, column=2)
            bars[k] = (c, val, colors[k])
        row = tk.Frame(pw, bg=bgc)
        row.grid(row=7, column=0, columnspan=3, pady=(10, 0))
        for txt, kind in (("餵食", "feed"), ("洗澡", "bath"), ("玩耍", "play"), ("睡覺", "sleep")):
            tk.Button(row, text=txt, font=font, width=6, relief="groove", bg="#ffffff",
                      command=lambda k=kind: act(k)).pack(side="left", padx=4)
        holder = {}

        def upd():
            if not pw.winfo_exists():
                return
            fr = frames.get(st["name"], frames["idle0"])
            sc = valley(fr, t=st["tick"] // 10).resize((180 * vs, 100 * vs), Image.NEAREST)
            holder["img"] = ImageTk.PhotoImage(sc)
            scene.configure(image=holder["img"])
            days = int((time.time() - care.born) // 86400) + 1
            mood = {"food": "肚子餓了…", "bath": "想洗澡…", "play": "好無聊…", "sleep": "好睏…"}.get(care.need(), "心情不錯 ♪")
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

    menu = tk.Menu(root, tearoff=0)
    menu.add_command(label="無夢之夢（狀態）", command=open_panel)
    menu.add_separator()
    for txt, kind in (("餵食", "feed"), ("洗澡", "bath"), ("玩耍", "play"), ("睡覺", "sleep"), ("種月光花", "plant")):
        menu.add_command(label=txt, command=lambda k=kind: act(k))
    menu.add_separator()
    walk_var = tk.BooleanVar(value=True)

    def toggle_walk():
        st["walk"] = walk_var.get()
        if not st["walk"] and st["mode"] in ("walk", "goto", "climb"):
            set_mode("idle", 60)
    menu.add_checkbutton(label="自由散步、爬視窗", variable=walk_var, command=toggle_walk)
    size = tk.Menu(menu, tearoff=0)
    for sc, lb in ((max(1, round(1.5 * dpi)), "小"), (max(2, round(2 * dpi)), "中"), (max(3, round(3 * dpi)), "大")):
        size.add_command(label=lb, command=lambda sc=sc: (st.update(scale=sc), cache.clear(), fcache.clear()))
    menu.add_cascade(label="大小", menu=size)
    menu.add_separator()

    def quit_():
        care.save()
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
    here = os.path.dirname(os.path.abspath(__file__))
    frames = build_frames()
    if "--sheet" in sys.argv:
        export_sheet(frames, here)
        print("exported", os.path.join(here, "spritesheet.png"))
    else:
        run_pet(frames)
