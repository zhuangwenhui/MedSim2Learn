"""Real laparoscopic video -> image-force .pt dataset (synt-compatible contract).

Source: the purified corpus under ``<real_origin_root>/{visual_data/NN.mp4,
force_data/NN.csv}`` produced by the Data Processpor pipeline (step1 copy +
step2 alignment check). Frame ``i`` of ``NN.mp4`` pairs 1:1 with row ``i`` of
``NN.csv`` (fx,fy,fz raw sensor Newtons); the alignment ``frame_count ==
force_rows`` is assumed pre-validated (a mismatch only truncates to the shorter
length, with a warning).

Each frame is center-cropped to the square endoscope field of view, masked to
the inscribed circle, and resized to ``size`` (default 256) so the real and
synt streams share one input spec. Per-sequence output mirrors
``twin_full/seqNN`` (``png/`` + ``labels.csv`` + ``dataset/preprocessed_batch_*.pt``)
so the existing ``assemble`` step merges real and synt the same way.
"""

import csv as _csv
import os
import shutil

import cv2
import numpy as np

from .dataset.serialize import serialize_labels_dataset


def circular_square_crop(frame, size, mask=True):
    """Center-crop to the square endoscope FOV, mask to the circle, resize.

    Returns an ``(size, size, 3)`` uint8 image. ``mask`` zeroes the corners
    outside the inscribed circle so the real vignette and the (white-background)
    synt renders share an identical circular field of view.
    """
    h, w = frame.shape[:2]
    s = min(h, w)
    y0 = (h - s) // 2
    x0 = (w - s) // 2
    out = cv2.resize(frame[y0:y0 + s, x0:x0 + s], (size, size),
                     interpolation=cv2.INTER_AREA)
    if mask:
        yy, xx = np.ogrid[:size, :size]
        c = (size - 1) / 2.0
        r = size / 2.0
        inside = (xx - c) ** 2 + (yy - c) ** 2 <= r * r
        out = out.copy()
        out[~inside] = 0
    return out


def load_forces(csv_path):
    """Load ``NN.csv`` -> ``(N, 3)`` float32 array ``[fx, fy, fz]`` (no header)."""
    rows = []
    with open(csv_path, "r", encoding="utf-8", errors="ignore") as fh:
        for line in fh:
            text = line.strip()
            if not text:
                continue
            parts = [p for p in text.split(",") if p.strip() != ""]
            if len(parts) < 3:
                raise ValueError(f"{csv_path}: row has <3 values: {text!r}")
            rows.append([float(parts[0]), float(parts[1]), float(parts[2])])
    if not rows:
        raise ValueError(f"no force rows in {csv_path}")
    return np.asarray(rows, dtype=np.float32)


def extract_sequence(seq_id, mp4_path, csv_path, out_seq_dir, size=256, mask=True):
    """Extract one real sequence to ``png/`` + ``labels.csv`` (frame i <-> force i).

    Returns ``(n_written, png_dir, labels_path)``.
    """
    forces = load_forces(csv_path)
    cap = cv2.VideoCapture(mp4_path)
    if not cap.isOpened():
        raise RuntimeError(f"cannot open video: {mp4_path}")
    n_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    n = min(n_frames, len(forces))
    if n_frames != len(forces):
        print(f"  [warn] seq {seq_id}: frame_count {n_frames} != force_rows "
              f"{len(forces)}; pairing first {n}")

    png_dir = os.path.join(out_seq_dir, "png")
    os.makedirs(png_dir, exist_ok=True)
    labels_path = os.path.join(out_seq_dir, "labels.csv")

    written = 0
    with open(labels_path, "w", newline="", encoding="utf-8") as lf:
        writer = _csv.writer(lf)
        writer.writerow(["SampleID", "force_x", "force_y", "force_z"])
        for i in range(n):
            ok, frame = cap.read()
            if not ok:
                print(f"  [warn] seq {seq_id}: frame read stopped at {i}/{n}")
                break
            img = circular_square_crop(frame, size, mask=mask)
            sid = f"real_s{seq_id}_v{i:04d}"
            # cv2 writes the BGR array as a correct RGB PNG (PIL reads it as RGB).
            cv2.imwrite(os.path.join(png_dir, sid + ".png"), img)
            fx, fy, fz = forces[i]
            writer.writerow([sid, f"{fx:.9g}", f"{fy:.9g}", f"{fz:.9g}"])
            written += 1
    cap.release()
    return written, png_dir, labels_path


def build_sequence(seq_id, mp4_path, csv_path, out_seq_dir, size=256, mask=True):
    """Extract + serialize one real sequence to ``out_seq_dir`` (png/labels/dataset)."""
    written, png_dir, labels_path = extract_sequence(
        seq_id, mp4_path, csv_path, out_seq_dir, size=size, mask=mask)
    data_dir = os.path.join(out_seq_dir, "dataset")
    serialize_labels_dataset(png_dir, labels_path, data_dir, resize=None)
    print(f"real seq {seq_id}: {written} frames @ {size}px -> {data_dir}")
    return written


def build_from_pngs(seq_id, src_png_dir, labels_csv, out_seq_dir, size=256, mask=True):
    """Re-process already-rendered PNGs to the shared size + circular-FOV spec.

    Used to align the synt twin renders (native 800px, square, white background)
    to the real 256px circular-mask input spec without re-running the offscreen
    renderer: each source PNG is downscaled to ``size`` and masked to the
    inscribed circle, the SampleID->force ``labels.csv`` is reused verbatim, and
    the result is serialized to the same KiDKNet ``.pt`` contract. Returns the
    number of frames processed.
    """
    out_png = os.path.join(out_seq_dir, "png")
    os.makedirs(out_png, exist_ok=True)
    names = sorted(f for f in os.listdir(src_png_dir) if f.lower().endswith(".png"))
    if not names:
        raise ValueError(f"no PNGs in {src_png_dir}")
    for name in names:
        img = cv2.imread(os.path.join(src_png_dir, name))
        if img is None:
            raise RuntimeError(f"cannot read PNG {os.path.join(src_png_dir, name)}")
        cv2.imwrite(os.path.join(out_png, name),
                    circular_square_crop(img, size, mask=mask))
    out_labels = os.path.join(out_seq_dir, "labels.csv")
    shutil.copy2(labels_csv, out_labels)
    data_dir = os.path.join(out_seq_dir, "dataset")
    serialize_labels_dataset(out_png, out_labels, data_dir, resize=None)
    print(f"reprocess seq {seq_id}: {len(names)} frames @ {size}px -> {data_dir}")
    return len(names)


def _self_test():
    """circular_square_crop shape + circular mask; raises AssertionError on failure."""
    frame = np.full((360, 640, 3), 200, np.uint8)
    out = circular_square_crop(frame, 256, mask=True)
    assert out.shape == (256, 256, 3), "crop output shape"
    assert int(out[0, 0].sum()) == 0, "corner must be masked to black"
    assert int(out[128, 128].sum()) > 0, "center must be kept"
    out_nomask = circular_square_crop(frame, 256, mask=False)
    assert int(out_nomask[0, 0].sum()) > 0, "no-mask corner kept"
    print("realvideo self-test PASS")
