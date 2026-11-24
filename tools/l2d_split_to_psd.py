"""
Live2D-style PSD split from finished art + color underpaint (色分け).

Workflow (matches common Cubism prep):
1. Source art PNG (transparent or black bg)
2. Flat color underpaint PNG aligned to same canvas (each part = unique RGB)
3. Script masks art by each palette color → unique named layers
4. Write import-ready PSD (RGB, one layer per part, no duplicate names)

Usage:
  python tools/l2d_split_to_psd.py
  python tools/l2d_split_to_psd.py --view 01_front
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from l2d_part_palette import (  # noqa: E402
    PART_PALETTE,
    PSD_STACK_ORDER,
    palette_legend_image,
)

# pytoshop packbits patch
import pytoshop.codecs as codecs  # noqa: E402
import packbits  # noqa: E402

codecs.packbits = packbits

from pytoshop.user import nested_layers  # noqa: E402
import pytoshop.enums as enums  # noqa: E402
from psd_tools import PSDImage  # noqa: E402

PSD_DIR = ROOT / "assets" / "six_views" / "l2d_psd"
VIEWS_DIR = PSD_DIR / "sources"
UNDER_DIR = PSD_DIR / "underpaint"
PARTS_DIR = PSD_DIR / "parts"
COLOR_TOL = 48  # underpaint AI colors are approximate


def ensure_rgba(img: Image.Image) -> Image.Image:
    return img.convert("RGBA")


def character_mask(art: np.ndarray) -> np.ndarray:
    """Non-background pixels (black canvas art)."""
    rgb = art[:, :, :3].astype(np.float32)
    bri = rgb.mean(axis=2)
    alpha = art[:, :, 3]
    if alpha.min() < 255:
        return alpha > 8
    return bri > 12


def match_color_mask(under: np.ndarray, rgb: tuple[int, int, int], tol: int) -> np.ndarray:
    target = np.array(rgb, dtype=np.float32)
    diff = np.abs(under[:, :, :3].astype(np.float32) - target).sum(axis=2)
    return diff <= tol


def nearest_palette_label(under: np.ndarray, char: np.ndarray) -> dict[str, np.ndarray]:
    """Assign each character pixel to nearest palette color; return masks."""
    h, w = under.shape[:2]
    colors = np.array([c for _, c in PART_PALETTE], dtype=np.float32)
    names = [n for n, _ in PART_PALETTE]
    pix = under[:, :, :3].astype(np.float32)
    # distance to each palette color: (H,W,P)
    dist = np.linalg.norm(pix[:, :, None, :] - colors[None, None, :, :], axis=3)
    nearest = dist.argmin(axis=2)
    min_dist = dist.min(axis=2)
    # only keep reasonably close matches on character
    masks: dict[str, np.ndarray] = {}
    for i, name in enumerate(names):
        m = char & (nearest == i) & (min_dist < COLOR_TOL * 2.2)
        if m.any():
            masks[name] = m
    return masks


def extract_part(art: np.ndarray, mask: np.ndarray, dilate: int = 1) -> np.ndarray:
    from scipy import ndimage

    if dilate > 0:
        mask = ndimage.binary_dilation(mask, iterations=dilate)
    out = np.zeros_like(art)
    out[mask] = art[mask]
    # if art has opaque black bg, force non-mask to transparent
    out[~mask, 3] = 0
    return out


def clean_dust(arr: np.ndarray, min_size: int = 24) -> np.ndarray:
    """Remove tiny speckles (Live2D_Cleaning analog)."""
    from scipy import ndimage

    alpha = arr[:, :, 3] > 8
    if not alpha.any():
        return arr
    labeled, n = ndimage.label(alpha)
    if n == 0:
        return arr
    sizes = ndimage.sum(alpha, labeled, range(1, n + 1))
    keep = np.zeros(n + 1, dtype=bool)
    for i, sz in enumerate(sizes, start=1):
        if sz >= min_size:
            keep[i] = True
    drop = ~keep[labeled]
    arr = arr.copy()
    arr[drop] = [0, 0, 0, 0]
    return arr


def trim_transparent_bbox(arr: np.ndarray) -> tuple[np.ndarray, tuple[int, int, int, int]]:
    """Return cropped array and (top, left, bottom, right) in full canvas coords."""
    a = arr[:, :, 3] > 0
    if not a.any():
        return arr, (0, 0, arr.shape[0], arr.shape[1])
    ys, xs = np.where(a)
    top, bottom = int(ys.min()), int(ys.max()) + 1
    left, right = int(xs.min()), int(xs.max()) + 1
    return arr[top:bottom, left:right].copy(), (top, left, bottom, right)


def write_psd(layers: list[tuple[str, np.ndarray]], out_path: Path, canvas: tuple[int, int]) -> None:
    """Write PSD; layers listed bottom→top."""
    h, w = canvas
    psd_layers = []
    for name, arr in layers:
        if arr[:, :, 3].max() == 0:
            continue
        crop, (top, left, bottom, right) = trim_transparent_bbox(arr)
        # pad safety
        ch = {
            -1: np.ascontiguousarray(crop[:, :, 3]),
            0: np.ascontiguousarray(crop[:, :, 0]),
            1: np.ascontiguousarray(crop[:, :, 1]),
            2: np.ascontiguousarray(crop[:, :, 2]),
        }
        psd_layers.append(
            nested_layers.Image(
                name=name[:63],
                top=top,
                left=left,
                bottom=bottom,
                right=right,
                channels=ch,
                opacity=255,
                visible=True,
            )
        )
    if not psd_layers:
        raise RuntimeError(f"no layers for {out_path}")

    psd = nested_layers.nested_layers_to_psd(
        psd_layers,
        color_mode=enums.ColorMode.rgb,
        compression=enums.Compression.rle,
        size=(w, h),
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "wb") as f:
        psd.write(f)


def verify_psd(path: Path) -> dict:
    psd = PSDImage.open(path)
    names = []
    ok = 0
    for layer in psd:
        names.append(layer.name.rstrip("\x00"))
        try:
            im = layer.topil()
            a = np.array(im)
            if a[..., -1].max() > 0 or a[..., :3].max() > 0:
                ok += 1
        except Exception:
            pass
    dup = len(names) - len(set(names))
    return {"layers": len(names), "ok_pixels": ok, "dups": dup, "names": names}


def process_view(view: str, save_part_pngs: bool = True) -> Path:
    art_path = VIEWS_DIR / f"{view}.png"
    under_path = UNDER_DIR / f"{view}_underpaint.png"
    if not art_path.exists():
        raise FileNotFoundError(art_path)
    if not under_path.exists():
        raise FileNotFoundError(under_path)

    art = np.array(ensure_rgba(Image.open(art_path)))
    under = np.array(ensure_rgba(Image.open(under_path).resize(art.shape[1::-1], Image.Resampling.NEAREST)))
    if under.shape[:2] != art.shape[:2]:
        under = np.array(
            Image.fromarray(under).resize((art.shape[1], art.shape[0]), Image.Resampling.NEAREST)
        )

    char = character_mask(art)
    masks = nearest_palette_label(under, char)

    part_dir = PARTS_DIR / view
    if save_part_pngs:
        part_dir.mkdir(parents=True, exist_ok=True)

    stacked: list[tuple[str, np.ndarray]] = []
    for name in PSD_STACK_ORDER:
        if name not in masks:
            continue
        part = clean_dust(extract_part(art, masks[name], dilate=1))
        if part[:, :, 3].sum() == 0:
            continue
        stacked.append((name, part))
        if save_part_pngs:
            Image.fromarray(part).save(part_dir / f"{name}.png")

    # Also keep a reference composite layer at bottom for QA (prefixed so unique)
    ref = art.copy()
    ref[~char, 3] = 0
    # put reference under everything? Cubism users often don't want full ref.
    # Skip full ref to avoid duplicate content; write preview separately.
    Image.fromarray(ref).save(PARTS_DIR / f"{view}_preview_cutout.png")

    out = PSD_DIR / f"{view}_import.psd"
    write_psd(stacked, out, (art.shape[0], art.shape[1]))
    info = verify_psd(out)
    print(f"{view}: wrote {out.name} layers={info['layers']} ok={info['ok_pixels']} dups={info['dups']}")
    if info["dups"]:
        print("  WARNING duplicate names", info["names"])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--view", help="single view id e.g. 01_front")
    ap.add_argument("--legend", action="store_true", help="only write palette legend")
    args = ap.parse_args()

    UNDER_DIR.mkdir(parents=True, exist_ok=True)
    PARTS_DIR.mkdir(parents=True, exist_ok=True)
    PSD_DIR.mkdir(parents=True, exist_ok=True)

    legend = palette_legend_image()
    legend_path = UNDER_DIR / "palette_legend.png"
    legend.save(legend_path)
    print("legend", legend_path)

    if args.legend:
        return

    views = [args.view] if args.view else sorted(p.stem for p in VIEWS_DIR.glob("*.png"))
    for view in views:
        try:
            process_view(view)
        except FileNotFoundError as e:
            print(f"SKIP {view}: {e}")


if __name__ == "__main__":
    main()
