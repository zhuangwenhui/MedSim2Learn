"""Native-resolution tissue corpus extraction from Origin_data mp4s.

Replaces the pilot corpus (160px crops cut from 256px serialized frames,
the diagnosed resolution ceiling): crops are cut at NATIVE mp4 scale.
Measured geometry: frames 640x360, FOV circle diameter ~516px (clipped
top/bottom), so serialization downscaled ~2.0x. A 320px native crop
covers the old 160px footprint at 2x linear detail; LoRA upsample to
512 drops from 3.2x to 1.6x.

seq04 is permanently excluded by the repository owner (black source).

Products (scratchpad; crops uploaded for DINOv2+CLIP purification):
  crops/  NN_fFFFF_xXXX_yYYY_sSSS.png  native tissue candidates (loose filter)
  sheets/ NN_fFFFF.png                 full-FOV content, top-clean frames
  manifest_crops.csv / manifest_sheets.csv / contact sheets
"""
import csv
import glob
import os

import cv2
import numpy as np

SRC = "D:/Data Processor/Origin_data/visual_data"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "native_corpus_v1")
STRIDE = 24          # process every 24th frame (0.8 s at 30 fps)
MARGIN = 24          # native-px guard against the circular vignette edge
BLACK_MAX = 0.05     # loose filters -- semantic scrub happens on the server
# Native-res recalibration: the pilot's (V>200, S<60) heuristic saturates
# at native scale (median 28.7% -- serialization downscale had been
# averaging specular glare below the threshold). Hard glare/steel cores
# (V>235, S<45) sit at median 7.5% / p90 9.7% on tissue, so 0.12 rejects
# instrument-dominated crops while keeping the normal glare baseline.
METAL_MAX = 0.12
CROPS_PER_SEQ = 110  # uniform temporal subsample cap per sequence
SHEETS_PER_SEQ = 4
SHEET_MIN_GAP = 100  # frames between selected sheets of one sequence


def fit_circle(mask):
    """Fit FOV circle (cx, cy, R) from a max-projected bright mask.

    Row chord widths obey (w/2)^2 + y^2 = (R^2 - cy^2) + 2*cy*y, linear
    in y -- least squares over rows with a substantial chord.
    """
    ys, a, b = [], [], []
    for y in range(mask.shape[0]):
        xs = np.nonzero(mask[y])[0]
        if len(xs) < 100:
            continue
        half = (xs.max() - xs.min()) / 2.0
        ys.append(y)
        a.append([1.0, float(y)])
        b.append(half * half + y * y)
    coef, *_ = np.linalg.lstsq(np.asarray(a), np.asarray(b), rcond=None)
    cy = coef[1] / 2.0
    r = np.sqrt(coef[0] + cy * cy)
    rows = np.nonzero(mask.sum(axis=1) > 100)[0]
    mid = rows[len(rows) // 2]
    xs = np.nonzero(mask[mid])[0]
    cx = (xs.min() + xs.max()) / 2.0
    return cx, cy, r


def corners_ok(x0, y0, s, cx, cy, r):
    for x, y in ((x0, y0), (x0 + s, y0), (x0, y0 + s), (x0 + s, y0 + s)):
        if (x - cx) ** 2 + (y - cy) ** 2 > (r - MARGIN) ** 2:
            return False
    return True


def frac_stats(bgr):
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    black = float((gray < 20).mean())
    metal = float(((hsv[..., 2] > 235) & (hsv[..., 1] < 45)).mean())
    return black, metal, float(gray.mean())


def candidate_boxes(cx, cy, w, h):
    """Candidate boxes centered on the FITTED circle center per sequence.

    The first run hardcoded a y-grid for an assumed cy=179.5; the real
    centers sit at cy=188..204, so every top corner clipped the vignette
    and zero crops survived. Boxes are now generated from (cx, cy).
    """
    boxes = []
    for s, dxs, dys in (
            (320, (-16, 0, 16), (-12, 0, 12)),
            (288, (-48, -24, 0, 24, 48), (-24, -12, 0, 12, 24)),
            (256, (-72, -36, 0, 36, 72), (-36, -18, 0, 18, 36))):
        for dx in dxs:
            for dy in dys:
                boxes.append((int(round(cx - s / 2)) + dx,
                              int(round(cy - s / 2)) + dy, s))
    return [(x0, y0, s) for x0, y0, s in boxes
            if 0 <= x0 and x0 + s <= w and 0 <= y0 and y0 + s <= h]


def main():
    os.makedirs(os.path.join(OUT, "crops"), exist_ok=True)
    os.makedirs(os.path.join(OUT, "sheets"), exist_ok=True)
    crop_rows, sheet_rows = [], []
    for path in sorted(glob.glob(os.path.join(SRC, "*.mp4"))):
        seq = os.path.basename(path)[:2]
        if seq == "04":  # permanently excluded by owner (black source)
            continue
        cap = cv2.VideoCapture(path)
        n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        # circle fit from 12 evenly spaced frames (max projection)
        acc = np.zeros((h, w), dtype=np.uint8)
        for idx in np.linspace(50, n - 50, 12).astype(int):
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(idx))
            ok, fr = cap.read()
            if ok:
                g = cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY)
                acc = np.maximum(acc, (g > 14).astype(np.uint8))
        cx, cy, r = fit_circle(acc)
        yy, xx = np.mgrid[0:h, 0:w]
        circle = ((xx - cx) ** 2 + (yy - cy) ** 2 <= r * r)
        boxes = candidate_boxes(cx, cy, w, h)
        sheet_x0 = max(0, int(cx - r))
        sheet_x1 = min(w, int(cx + r) + 1)
        seq_sheets, seq_crops = [], []
        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        for i in range(n):
            if not cap.grab():
                break
            if i % STRIDE:
                continue
            ok, fr = cap.retrieve()
            if not ok:
                continue
            kept = []
            for x0, y0, s in boxes:
                if not corners_ok(x0, y0, s, cx, cy, r):
                    continue
                crop = fr[y0:y0 + s, x0:x0 + s]
                black, metal, lum = frac_stats(crop)
                if black <= BLACK_MAX and metal <= METAL_MAX:
                    kept.append((metal, black, lum, x0, y0, s, crop))
            kept.sort(key=lambda t: t[0])
            chosen = []
            for cand in kept:
                if len(chosen) == 2:
                    break
                if chosen and abs(cand[3] - chosen[0][3]) < 96 \
                        and abs(cand[4] - chosen[0][4]) < 96:
                    continue
                chosen.append(cand)
            for metal, black, lum, x0, y0, s, crop in chosen:
                seq_crops.append((i, x0, y0, s, metal, black, lum, crop))
            # sheet score over the FOV circle content
            g = cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY)
            hsv = cv2.cvtColor(fr, cv2.COLOR_BGR2HSV)
            hard_glare = (hsv[..., 2] > 235) & (hsv[..., 1] < 45)
            metal_c = float(hard_glare[circle].mean())
            black_c = float((g < 20)[circle].mean())
            seq_sheets.append((metal_c + black_c, metal_c, black_c, i,
                               fr[:, sheet_x0:sheet_x1].copy()))
        cap.release()
        # uniform temporal subsample keeps the pool bounded per sequence
        if len(seq_crops) > CROPS_PER_SEQ:
            picks = np.linspace(0, len(seq_crops) - 1,
                                CROPS_PER_SEQ).astype(int)
            seq_crops = [seq_crops[j] for j in picks]
        for i, x0, y0, s, metal, black, lum, crop in seq_crops:
            name = f"{seq}_f{i:04d}_x{x0}_y{y0}_s{s}.png"
            cv2.imwrite(os.path.join(OUT, "crops", name), crop)
            crop_rows.append([name, seq, i, x0, y0, s,
                              f"{metal:.4f}", f"{black:.4f}", f"{lum:.1f}"])
        seq_sheets.sort(key=lambda t: t[0])
        picked = []
        for score, metal_c, black_c, idx, img in seq_sheets:
            if len(picked) == SHEETS_PER_SEQ:
                break
            if any(abs(idx - p[0]) < SHEET_MIN_GAP for p in picked):
                continue
            picked.append((idx, score))
            name = f"{seq}_f{idx:04d}.png"
            cv2.imwrite(os.path.join(OUT, "sheets", name), img)
            sheet_rows.append([name, seq, idx, f"{metal_c:.4f}", f"{black_c:.4f}"])
        print(f"seq {seq}: circle cx={cx:.1f} cy={cy:.1f} r={r:.1f} "
              f"crops+={sum(1 for c in crop_rows if c[1] == seq)} "
              f"sheets={len(picked)}", flush=True)
    for fname, rows, hdr in (
            ("manifest_crops.csv", crop_rows,
             ["file", "seq", "frame", "x0", "y0", "size", "metal", "black", "lum"]),
            ("manifest_sheets.csv", sheet_rows,
             ["file", "seq", "frame", "metal", "black"])):
        with open(os.path.join(OUT, fname), "w", newline="") as f:
            wtr = csv.writer(f)
            wtr.writerow(hdr)
            wtr.writerows(rows)
    print(f"TOTAL crops={len(crop_rows)} sheets={len(sheet_rows)}", flush=True)


if __name__ == "__main__":
    main()
