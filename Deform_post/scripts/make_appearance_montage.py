"""Contact-sheet montage for appearance-DR renders vs the production baseline.

Rows are render variants (optionally headed by a baseline row and tailed by a
real-corpus reference row), columns are frames. Frames are picked by index
into the FIRST variant directory's sorted PNG listing and matched BY STEM in
every other variant row, so each column compares the same deformation frame
across variants. The optional --real-dir row is matched BY POSITION in its
own sorted listing instead (real stems differ from twin stems; the corpora
pair frame i <-> frame i). Pure PIL + numpy; no Open3D.

Usage:
  python scripts/make_appearance_montage.py --out sheet.png \
      [--baseline DIR] [--real-dir DIR] --dirs label1=dir1 [label2=dir2 ...] \
      [--frames 0,343,686] [--num-frames 6] [--thumb 256]
"""

import argparse
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

LABEL_GUTTER = 140
HEADER_H = 20
PAD = 4


def _parse_dirs(specs):
    rows = []
    for spec in specs:
        if "=" not in spec:
            raise SystemExit(f"--dirs entries must be label=path, got {spec!r}")
        label, path = spec.split("=", 1)
        if not os.path.isdir(path):
            raise SystemExit(f"render dir not found: {path}")
        rows.append((label, path))
    return rows


def _sorted_stems(png_dir):
    stems = sorted(
        os.path.splitext(f)[0]
        for f in os.listdir(png_dir) if f.lower().endswith(".png"))
    if not stems:
        raise SystemExit(f"no PNGs in {png_dir}")
    return stems


def _pick_frames(stems, frames_arg, num_frames):
    if frames_arg:
        indices = [int(tok) for tok in frames_arg.split(",") if tok.strip()]
    else:
        n = min(num_frames, len(stems))
        indices = [int(round(i * (len(stems) - 1) / max(n - 1, 1)))
                   for i in range(n)]
    for idx in indices:
        if not 0 <= idx < len(stems):
            raise SystemExit(
                f"frame index {idx} outside the variant listing "
                f"(0..{len(stems) - 1})")
    return indices


def _load_thumb(png_dir, stem, thumb):
    path = os.path.join(png_dir, stem + ".png")
    if not os.path.isfile(path):
        raise SystemExit(f"stem {stem!r} missing in {png_dir}")
    with Image.open(path) as img:
        return img.convert("RGB").resize((thumb, thumb), Image.LANCZOS)


def build_montage(rows, indices, thumb):
    """Assemble the contact sheet; returns a PIL image.

    ``rows`` entries are ``(label, png_dir, match_mode)`` with match_mode
    "stem" (variant rows: the reference stem must exist in the dir) or
    "index" (the real reference row: pick by position in the dir's own
    sorted listing).
    """
    reference_stems = _sorted_stems(
        next(png_dir for _label, png_dir, mode in rows if mode == "stem"))
    stems = [reference_stems[i] for i in indices]
    n_cols = len(stems)
    width = LABEL_GUTTER + n_cols * (thumb + PAD) + PAD
    height = HEADER_H + len(rows) * (thumb + PAD) + PAD
    sheet = Image.new("RGB", (width, height), (24, 24, 24))
    draw = ImageDraw.Draw(sheet)
    for col, (idx, stem) in enumerate(zip(indices, stems)):
        x = LABEL_GUTTER + PAD + col * (thumb + PAD)
        draw.text((x, 4), f"frame {idx} ({stem})", fill=(220, 220, 220))
    for row, (label, png_dir, mode) in enumerate(rows):
        y = HEADER_H + PAD + row * (thumb + PAD)
        draw.text((8, y + thumb // 2 - 6), label, fill=(220, 220, 220))
        if mode == "index":
            own_stems = _sorted_stems(png_dir)
            row_stems = []
            for idx in indices:
                if idx >= len(own_stems):
                    raise SystemExit(
                        f"frame index {idx} outside the {label} row listing "
                        f"(0..{len(own_stems) - 1}) in {png_dir}")
                row_stems.append(own_stems[idx])
        else:
            row_stems = stems
        for col, stem in enumerate(row_stems):
            x = LABEL_GUTTER + PAD + col * (thumb + PAD)
            sheet.paste(_load_thumb(png_dir, stem, thumb), (x, y))
    return sheet


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Appearance-DR contact sheet (rows=variants, cols=frames)")
    parser.add_argument("--out", required=True, help="Output montage PNG path")
    parser.add_argument("--baseline", default=None,
                        help="Production baseline PNG dir (first row)")
    parser.add_argument("--real-dir", default=None,
                        help="Real-corpus reference PNG dir (last row, "
                             "frames matched by sorted position)")
    parser.add_argument("--dirs", nargs="+", required=True,
                        metavar="LABEL=DIR", help="Variant render PNG dirs")
    parser.add_argument("--frames", default=None,
                        help="Comma list of frame indices into the first "
                             "variant dir's sorted PNG listing")
    parser.add_argument("--num-frames", type=int, default=6,
                        help="Evenly spaced frame count when --frames is unset")
    parser.add_argument("--thumb", type=int, default=256,
                        help="Thumbnail edge length in pixels")
    args = parser.parse_args(argv)

    rows = [(label, path, "stem") for label, path in _parse_dirs(args.dirs)]
    if args.baseline is not None:
        if not os.path.isdir(args.baseline):
            raise SystemExit(f"baseline dir not found: {args.baseline}")
        rows = [("baseline", args.baseline, "stem")] + rows
    if args.real_dir is not None:
        if not os.path.isdir(args.real_dir):
            raise SystemExit(f"real dir not found: {args.real_dir}")
        rows = rows + [("real", args.real_dir, "index")]
    indices = _pick_frames(_sorted_stems(args.dirs[0].split("=", 1)[1]),
                           args.frames, args.num_frames)
    sheet = build_montage(rows, indices, args.thumb)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    sheet.save(args.out)
    arr = np.asarray(sheet)
    print(f"montage: {len(rows)} rows x {len(indices)} cols "
          f"({arr.shape[1]}x{arr.shape[0]}) -> {args.out}")


if __name__ == "__main__":
    sys.exit(main())
