"""Live2D 色分け palette — unique flat colors for scripted PSD split.

Naming follows common L2D import practice:
  [L|R_]partName  — unique, ASCII, no duplicate names
  Groups conceptually: hair / face / body / outfit / accessory
"""

from __future__ import annotations

# (layer_name, RGB) — colors must stay far apart for robust matching
PART_PALETTE: list[tuple[str, tuple[int, int, int]]] = [
    # hair (bottom → top in PSD usually back first)
    ("hair_back", (220, 20, 60)),
    ("hair_side_L", (255, 140, 0)),
    ("hair_side_R", (255, 215, 0)),
    ("bangs", (255, 255, 0)),
    ("braid_L", (154, 205, 50)),
    ("braid_R", (50, 205, 50)),
    ("ribbon_L", (0, 250, 154)),
    ("ribbon_R", (0, 255, 255)),
    # accessory
    ("wing_L", (30, 144, 255)),
    ("wing_R", (0, 0, 255)),
    # face
    ("ear_L", (138, 43, 226)),
    ("ear_R", (186, 85, 211)),
    ("face", (255, 105, 180)),
    ("forehead_mark", (255, 20, 147)),
    ("eye_white_L", (255, 250, 250)),
    ("eye_white_R", (245, 245, 245)),
    ("iris_L", (176, 196, 222)),
    ("iris_R", (119, 136, 153)),
    ("lash_L", (72, 61, 139)),
    ("lash_R", (75, 0, 130)),
    ("mouth", (219, 112, 147)),
    # body / outfit
    ("neck", (255, 228, 196)),
    ("collar", (230, 230, 250)),
    ("body", (47, 79, 79)),
    ("sleeve_L", (25, 25, 112)),
    ("sleeve_R", (70, 70, 140)),
    ("skirt", (0, 0, 80)),
    ("leg_L", (240, 248, 255)),
    ("leg_R", (176, 224, 230)),
    ("shoe_L", (20, 20, 20)),
    ("shoe_R", (60, 60, 60)),
]

PART_BY_NAME = {n: c for n, c in PART_PALETTE}
PART_BY_COLOR = {c: n for n, c in PART_PALETTE}

# Bottom → top draw order for PSD (back layers first)
PSD_STACK_ORDER = [
    "hair_back",
    "body",
    "skirt",
    "leg_L",
    "leg_R",
    "shoe_L",
    "shoe_R",
    "sleeve_L",
    "sleeve_R",
    "collar",
    "neck",
    "face",
    "ear_L",
    "ear_R",
    "forehead_mark",
    "eye_white_L",
    "eye_white_R",
    "iris_L",
    "iris_R",
    "lash_L",
    "lash_R",
    "mouth",
    "hair_side_L",
    "hair_side_R",
    "braid_L",
    "braid_R",
    "ribbon_L",
    "ribbon_R",
    "bangs",
    "wing_L",
    "wing_R",
]

# Which parts are expected per view (others optional if found)
VIEW_PARTS = {
    "01_front": None,  # all
    "02_front_three_quarter": None,
    "03_left": [
        "hair_back", "bangs", "hair_side_L", "braid_L", "ribbon_L",
        "wing_L", "ear_L", "face", "forehead_mark",
        "eye_white_L", "iris_L", "lash_L", "mouth",
        "neck", "collar", "body", "sleeve_L", "skirt",
        "leg_L", "shoe_L",
    ],
    "04_right": [
        "hair_back", "bangs", "hair_side_R", "braid_R", "ribbon_R",
        "wing_R", "ear_R", "face", "forehead_mark",
        "eye_white_R", "iris_R", "lash_R", "mouth",
        "neck", "collar", "body", "sleeve_R", "skirt",
        "leg_R", "shoe_R",
    ],
    "06_back": [
        "hair_back", "braid_L", "braid_R", "ribbon_L", "ribbon_R",
        "wing_L", "wing_R", "ear_L", "ear_R",
        "neck", "collar", "body", "sleeve_L", "sleeve_R", "skirt",
        "leg_L", "leg_R", "shoe_L", "shoe_R",
    ],
    "07_top": [
        "hair_back", "bangs", "braid_L", "braid_R", "ribbon_L", "ribbon_R",
        "wing_L", "wing_R", "ear_L", "ear_R", "face",
        "collar", "body", "sleeve_L", "sleeve_R", "skirt",
    ],
    "08_bottom": [
        "shoe_L", "shoe_R", "leg_L", "leg_R", "skirt",
        "body", "sleeve_L", "sleeve_R", "collar",
        "face", "hair_back", "braid_L", "braid_R", "wing_L", "wing_R",
    ],
}


def palette_legend_image(cell: int = 48, cols: int = 4):
    """Return a PIL legend image for prompts / QA."""
    from PIL import Image, ImageDraw, ImageFont

    rows = (len(PART_PALETTE) + cols - 1) // cols
    img = Image.new("RGB", (cols * 280, rows * cell), (0, 0, 0))
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("arial.ttf", 14)
    except OSError:
        font = ImageFont.load_default()
    for i, (name, rgb) in enumerate(PART_PALETTE):
        r, c = divmod(i, cols)
        x, y = c * 280 + 4, r * cell + 4
        draw.rectangle([x, y, x + cell - 8, y + cell - 8], fill=rgb)
        draw.text((x + cell, y + 12), f"{name} {rgb}", fill=(255, 255, 255), font=font)
    return img
