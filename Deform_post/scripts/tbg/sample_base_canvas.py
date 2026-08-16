"""Owner-ruled pipeline step 1-2: organ-only base sampling -> canvas.

Corrections vs the v4-P sampler: the sampling region is restricted to
the KIDNEY PROPER (previous mask deliberately included surrounding
peritoneal tissue -- ruled wrong). Small vessel-free, glare-free
patches are sampled from the organ surface; their colour statistics
(mean tones, patch-to-patch spread, within-patch grain) drive a
1024x1024 UV base canvas: smooth low-frequency tone field + fine
grain. No vessels here -- those are authored by the diffusion stage.

Outputs: base_canvas.png (UV atlas base), patch grid (for the human
gate), organ-proper mask debug overlay, stats npz.
"""
import os

import cv2
import numpy as np

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                    "native_corpus_v1")
OUT = os.path.join(BASE, "base_canvas")
SHEET = os.environ.get("SHEET", "01_f0432")
PATCH = 48
N_KEEP = 24
TEX = 1024


# Hand-authored kidney-proper ellipse per sheet frame (owner ruling:
# sampling must stay on the ORGAN ITSELF -- colour heuristics cannot
# separate kidney capsule from equally-pink peritoneal membrane).
# (cx, cy, ax, ay, angle_deg) in native sheet pixels.
KIDNEY_ELLIPSE = {
    "01_f0432": (285, 235, 145, 100, -8.0),
}


def kidney_proper_mask(bgr, sheet):
    """Hand ellipse intersected with brightness sanity, then erode."""
    cx, cy, ax, ay, ang = KIDNEY_ELLIPSE[sheet]
    m = np.zeros(bgr.shape[:2], np.uint8)
    cv2.ellipse(m, (cx, cy), (ax, ay), ang, 0, 360, 1, cv2.FILLED)
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    m &= (gray > 35).astype(np.uint8)  # drop the dark hilum crevice
    return cv2.erode(m, np.ones((9, 9), np.uint8)).astype(bool)


def sample_patches(bgr, mask):
    """Rank patches by base-pixel purity; keep a per-pixel base mask.

    A 48px window free of BOTH glare speckle and vessels does not exist
    on this surface (diagnosed: median patch has a 255 pixel and ~6%
    dark pixels). So instead of demanding clean patches, each patch
    excludes its glare (V>238) and vessel (dark) pixels and the BASE
    statistics come from the remainder; patches rank by remainder
    fraction.
    """
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY).astype(np.float32)
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    v = hsv[..., 2].astype(np.float32)
    cands = []
    h, w = mask.shape
    for y0 in range(0, h - PATCH, PATCH // 2):
        for x0 in range(0, w - PATCH, PATCH // 2):
            sub = mask[y0:y0 + PATCH, x0:x0 + PATCH]
            if not bool(sub.all()):
                continue
            pv = v[y0:y0 + PATCH, x0:x0 + PATCH]
            pg = gray[y0:y0 + PATCH, x0:x0 + PATCH]
            keep = (pv <= 238) & (pg >= 0.72 * pg.mean())
            frac = float(keep.mean())
            if frac < 0.6:
                continue
            cands.append((-frac, y0, x0, keep))
    cands.sort(key=lambda t: t[0])
    return cands[:N_KEEP]


def build_canvas(bgr, picks, rng):
    means, grains = [], []
    for _, y0, x0, keep in picks:
        px = bgr[y0:y0 + PATCH, x0:x0 + PATCH][keep].astype(np.float64)
        means.append(px.mean(axis=0))
        grains.append(px.std(axis=0).mean())
    means = np.array(means) / 255.0
    grain = float(np.mean(grains)) / 255.0
    # smooth low-frequency field blends the sampled tones across the
    # atlas; amplitude comes from the real patch-to-patch spread
    field = cv2.GaussianBlur(
        rng.standard_normal((TEX, TEX)).astype(np.float32), (0, 0), 90)
    field = (field - field.min()) / (field.max() - field.min() + 1e-6)
    order = np.argsort(means.sum(axis=1))
    lo = means[order[max(0, len(order) // 10)]]
    hi = means[order[min(len(order) - 1, 9 * len(order) // 10)]]
    canvas = (lo[None, None] * (1 - field[..., None])
              + hi[None, None] * field[..., None])
    canvas += rng.standard_normal((TEX, TEX, 3)).astype(np.float32) \
        * grain * 0.55
    canvas = cv2.GaussianBlur(canvas.clip(0, 1), (3, 3), 0)
    return canvas, means, grain


def main():
    os.makedirs(OUT, exist_ok=True)
    bgr = cv2.imread(f"{BASE}/sheets/{SHEET}.png")
    mask = kidney_proper_mask(bgr, SHEET)
    picks = sample_patches(bgr, mask)
    if len(picks) < 8:
        raise SystemExit(f"only {len(picks)} clean patches -- retune")
    rng = np.random.default_rng(20260815)
    canvas, means, grain = build_canvas(bgr, picks, rng)
    cv2.imwrite(f"{OUT}/base_canvas.png",
                (canvas * 255).astype(np.uint8))
    # texture-pool canvases: identical sampled statistics, per-texture
    # noise fields (seed = 1000 + k, one per production sequence)
    pool = int(os.environ.get("POOL", "0"))
    for k in range(pool):
        rng_k = np.random.default_rng(1000 + k)
        canvas_k, _, _ = build_canvas(bgr, picks, rng_k)
        cv2.imwrite(f"{OUT}/base_canvas_k{k:02d}.png",
                    (canvas_k * 255).astype(np.uint8))
    if pool:
        print(f"pool canvases: {pool}", flush=True)
    overlay = bgr.copy()
    edge = cv2.dilate(mask.astype(np.uint8), None) & ~mask
    overlay[edge.astype(bool)] = (0, 255, 0)
    for _, y0, x0, _keep in picks:
        cv2.rectangle(overlay, (x0, y0), (x0 + PATCH, y0 + PATCH),
                      (0, 0, 255), 1)
    cv2.imwrite(f"{OUT}/sampling_debug.png", overlay)
    tiles = [cv2.resize(bgr[y0:y0 + PATCH, x0:x0 + PATCH], (96, 96),
                        interpolation=cv2.INTER_NEAREST)
             for _, y0, x0, _keep in picks]
    while len(tiles) % 8:
        tiles.append(np.zeros((96, 96, 3), np.uint8))
    rows = [np.concatenate(tiles[i:i + 8], axis=1)
            for i in range(0, len(tiles), 8)]
    cv2.imwrite(f"{OUT}/patch_grid.png", np.concatenate(rows, axis=0))
    np.savez(f"{OUT}/base_stats.npz", means=means, grain=grain,
             mask=mask)
    print(f"BASE-CANVAS {len(picks)} patches, grain {grain:.4f}, "
          f"organ frac {mask.mean():.3f}", flush=True)


if __name__ == "__main__":
    main()
