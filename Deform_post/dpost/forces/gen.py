"""Real-referenced force trajectory synthesis.

The original repository sampled training forces from uniform boxes; the real
recordings show structured press-and-release waveforms instead. This module
generates NEW sensor-frame trajectories anchored to a real recording: each
variant is the source waveform under a controlled, invertible transform

    F_new(t) = s * R_jitter @ F_src(warp(t))

- amplitude scale s drawn from scale_range (keeps direction and shape)
- time warp resamples the sequence to round(N * w), w from warp_range
  (linear interpolation; stretches the rhythm without breaking continuity)
- R_jitter is a small random rotation (angle <= jitter_deg) applied rigidly
  to the whole trajectory (preserves |F| and smoothness exactly)

Because the transform is invertible, every generated variant is validated by
inverse-reconstructing the source and bounding the round-trip error, plus
envelope checks (peak magnitude and per-frame step stay within the scaled
source envelope). Validation stats land in the .gen.json next to each CSV.
A distribution-fitting mode (synthesize unrelated waveforms from source
statistics) is intentionally left unimplemented until a concrete need shows
up; see synthesize_from_stats.
"""

import json
import os

import numpy as np

from .real import load_real_forces


def _rotation_matrix(axis, angle_rad):
    """Rodrigues rotation matrix about `axis` (need not be unit)."""
    a = np.asarray(axis, float)
    a = a / np.linalg.norm(a)
    K = np.array([[0.0, -a[2], a[1]],
                  [a[2], 0.0, -a[0]],
                  [-a[1], a[0], 0.0]])
    return np.eye(3) + np.sin(angle_rad) * K + (1.0 - np.cos(angle_rad)) * (K @ K)


def _resample_length(F, n_new):
    """Linear-interpolate an (N, 3) trajectory onto n_new evenly spaced frames."""
    n_old = len(F)
    if n_new == n_old:
        return F.copy()
    t_old = np.linspace(0.0, 1.0, n_old)
    t_new = np.linspace(0.0, 1.0, n_new)
    out = np.empty((n_new, 3))
    for c in range(3):
        out[:, c] = np.interp(t_new, t_old, F[:, c])
    return out


def resample_trajectory(F_src, rng, scale_range=(0.8, 1.2),
                        warp_range=(0.9, 1.1), jitter_deg=5.0):
    """One synthetic variant of `F_src`; returns (F_new, params).

    params records the drawn scale, warp, jitter axis/angle and the rotation
    matrix so the transform can be inverted exactly.
    """
    F_src = np.asarray(F_src, float).reshape(-1, 3)
    scale = float(rng.uniform(*scale_range))
    warp = float(rng.uniform(*warp_range))
    angle_deg = float(rng.uniform(0.0, jitter_deg))
    axis = rng.normal(size=3)
    axis = axis / np.linalg.norm(axis)
    R = _rotation_matrix(axis, np.deg2rad(angle_deg))

    n_new = max(2, int(round(len(F_src) * warp)))
    F_new = scale * (R @ _resample_length(F_src, n_new).T).T
    params = {
        "scale": scale,
        "warp": warp,
        "n_src": int(len(F_src)),
        "n_new": int(n_new),
        "jitter_deg": angle_deg,
        "jitter_axis": [float(x) for x in axis],
        "R_jitter": [[float(x) for x in row] for row in R],
    }
    return F_new, params


def validate_resample(F_src, F_new, params, roundtrip_rel_tol=0.05,
                      peak_tol=1.001, step_tol=2.0):
    """Validate a variant against its source; raises ValueError on violation.

    - round-trip: unrotate/unscale/unwarp the variant and compare to the
      source; RMS error must stay below roundtrip_rel_tol * RMS(source)
      (linear interpolation both ways loses a little high-frequency content,
      nothing else is allowed to differ)
    - peak envelope: max |F_new| <= scale * max |F_src| * peak_tol
      (rotation preserves magnitude, so scaling is the only legal change)
    - smoothness: max per-frame step of the variant must stay within
      step_tol * scale / warp * the source's max step (warping compresses or
      stretches the time axis, anything beyond that bound is an artifact)

    Returns a stats dict for the provenance record.
    """
    F_src = np.asarray(F_src, float).reshape(-1, 3)
    F_new = np.asarray(F_new, float).reshape(-1, 3)
    R = np.asarray(params["R_jitter"], float)
    scale = float(params["scale"])
    warp = float(params["warp"])

    recon = _resample_length((R.T @ (F_new / scale).T).T, len(F_src))
    rms_src = float(np.sqrt(np.mean(F_src ** 2)))
    rms_err = float(np.sqrt(np.mean((recon - F_src) ** 2)))
    rel_err = rms_err / rms_src if rms_src > 0 else 0.0
    if rel_err > roundtrip_rel_tol:
        raise ValueError(
            f"round-trip reconstruction error {rel_err:.4f} exceeds "
            f"{roundtrip_rel_tol} (interp artifact or transform bug)")

    mag_src = np.linalg.norm(F_src, axis=1)
    mag_new = np.linalg.norm(F_new, axis=1)
    peak_bound = scale * float(mag_src.max()) * peak_tol
    if float(mag_new.max()) > peak_bound:
        raise ValueError(
            f"peak |F| {mag_new.max():.6g} exceeds the scaled source envelope "
            f"{peak_bound:.6g}")

    step_src = float(np.abs(np.diff(F_src, axis=0)).max()) if len(F_src) > 1 else 0.0
    step_new = float(np.abs(np.diff(F_new, axis=0)).max()) if len(F_new) > 1 else 0.0
    step_bound = step_tol * scale / warp * step_src
    if step_src > 0 and step_new > step_bound:
        raise ValueError(
            f"max per-frame step {step_new:.6g} exceeds bound {step_bound:.6g}")

    # |F| histogram distance (informative): the variant's magnitudes, unscaled,
    # against the source distribution. 0 = identical shapes.
    bins = np.linspace(0.0, max(mag_src.max(), 1e-12), 33)
    h_src, _ = np.histogram(mag_src, bins=bins, density=True)
    h_new, _ = np.histogram(mag_new / scale, bins=bins, density=True)
    width = bins[1] - bins[0]
    hist_l1 = float(np.abs(h_src - h_new).sum() * width)

    return {
        "roundtrip_rel_rms": rel_err,
        "peak_mag_src": float(mag_src.max()),
        "peak_mag_new": float(mag_new.max()),
        "max_step_src": step_src,
        "max_step_new": step_new,
        "mag_hist_l1_unscaled": hist_l1,
    }


def generate_variants(source_csv, out_dir, count, seed=20260613,
                      scale_range=(0.8, 1.2), warp_range=(0.9, 1.1),
                      jitter_deg=5.0):
    """Write `count` validated variants of `source_csv` into out_dir.

    Outputs per variant k (1-based): <stem>_rK.csv (bare fx,fy,fz rows, the
    same format prep consumes) and <stem>_rK.gen.json (drawn parameters +
    validation stats + provenance). Deterministic for a given seed. Returns
    the list of CSV paths.
    """
    F_src = load_real_forces(source_csv)
    stem = os.path.splitext(os.path.basename(source_csv))[0]
    os.makedirs(out_dir, exist_ok=True)
    rng = np.random.default_rng(seed)
    written = []
    for k in range(1, count + 1):
        F_new, params = resample_trajectory(
            F_src, rng, scale_range=scale_range, warp_range=warp_range,
            jitter_deg=jitter_deg)
        stats = validate_resample(F_src, F_new, params)

        csv_path = os.path.join(out_dir, f"{stem}_r{k}.csv")
        with open(csv_path, "w", newline="") as fh:
            for fx, fy, fz in F_new:
                fh.write(f"{fx:.8g},{fy:.8g},{fz:.8g}\n")

        meta = {
            "source_csv": os.path.abspath(source_csv),
            "variant": k,
            "seed": seed,
            "scale_range": list(scale_range),
            "warp_range": list(warp_range),
            "jitter_deg_max": jitter_deg,
            "params": params,
            "validation": stats,
        }
        meta_path = os.path.join(out_dir, f"{stem}_r{k}.gen.json")
        with open(meta_path, "w") as fh:
            json.dump(meta, fh, indent=2)

        print(f"forcegen: {stem}_r{k}.csv  n={params['n_new']} "
              f"scale={params['scale']:.3f} warp={params['warp']:.3f} "
              f"jitter={params['jitter_deg']:.2f}deg "
              f"roundtrip_rms={stats['roundtrip_rel_rms']:.4f} "
              f"hist_l1={stats['mag_hist_l1_unscaled']:.4f}")
        written.append(csv_path)
    return written


def synthesize_from_stats(*_args, **_kwargs):
    """Placeholder for the distribution-fitting mode.

    Intended approach when needed: fit per-axis amplitude distributions, the
    press-event envelope, and the |F| power spectrum of one or more real
    recordings, then synthesize new waveforms (envelope times PSD-matched
    noise) that match those statistics without replaying any single source.
    Not implemented; the resample mode covers the current training needs.
    """
    raise NotImplementedError(
        "fit-based force synthesis is not implemented; use generate_variants")


def _self_test():
    """Generator invariants on a press-like synthetic waveform; raises on failure."""
    import tempfile

    # Press-and-release-like source: smooth envelope, slight lateral noise.
    n = 600
    t = np.linspace(0.0, 4.0 * np.pi, n)
    rng0 = np.random.default_rng(3)
    F_src = np.stack([
        0.05 * np.sin(0.5 * t) + 0.01 * rng0.normal(size=n),
        0.04 * np.cos(0.3 * t) + 0.01 * rng0.normal(size=n),
        -0.5 * np.clip(np.sin(t * 0.5), 0.0, None) - 0.05,
    ], axis=1)

    rng = np.random.default_rng(11)
    F_new, params = resample_trajectory(F_src, rng)
    stats = validate_resample(F_src, F_new, params)
    assert stats["roundtrip_rel_rms"] < 0.05, "round-trip error too large"
    assert params["n_new"] == len(F_new)
    # Rotation preserves magnitudes: |F_new| == scale * warp(|F_src|).
    mag_new = np.linalg.norm(F_new, axis=1)
    mag_ref = params["scale"] * np.linalg.norm(
        _resample_length(F_src, params["n_new"]), axis=1)
    assert np.allclose(mag_new, mag_ref, rtol=1e-9), "rotation changed |F|"

    # Determinism + full file round-trip through generate_variants.
    with tempfile.TemporaryDirectory() as td:
        src = os.path.join(td, "07.csv")
        with open(src, "w", newline="") as fh:
            for fx, fy, fz in F_src:
                fh.write(f"{fx:.8g},{fy:.8g},{fz:.8g}\n")
        out_a = generate_variants(src, os.path.join(td, "a"), count=2, seed=99)
        out_b = generate_variants(src, os.path.join(td, "b"), count=2, seed=99)
        assert len(out_a) == 2
        for pa, pb in zip(out_a, out_b):
            with open(pa) as f1, open(pb) as f2:
                assert f1.read() == f2.read(), "same seed must reproduce output"
        # The generated CSV loads through the same reader prep uses.
        F_back = load_real_forces(out_a[0])
        assert F_back.shape[1] == 3 and len(F_back) >= 2
        meta = json.load(open(out_a[0].replace(".csv", ".gen.json")))
        assert meta["validation"]["roundtrip_rel_rms"] < 0.05

    # A corrupted variant must be rejected.
    F_bad = F_new.copy()
    F_bad[len(F_bad) // 2] *= 10.0
    try:
        validate_resample(F_src, F_bad, params)
        raise AssertionError("validate_resample accepted a corrupted variant")
    except ValueError:
        pass

    # fit mode is an explicit, documented stub.
    try:
        synthesize_from_stats()
        raise AssertionError("synthesize_from_stats should be unimplemented")
    except NotImplementedError:
        pass
    print("forces.gen self-test PASS")
