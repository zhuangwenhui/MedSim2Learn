"""Empirical force-envelope characterisation for the MedSim2Learn twin corpus.

Track A (force-prior) data half. Under the 2026-07-03 redirection the synthetic
training forces must stay tethered to what real operation actually produced: the
digital twin replays real sensor forces, so the twin force labels equal the
paired real sensor force by construction, and the REAL-domain forces fully
characterise the empirical reference envelope any force generator must respect.

The pipeline today polices force *identity* (correct image<->force pairing) but
never force *plausibility* (no NaN / range / physical-sanity guard). This module
supplies the missing acceptance gate:

  1. read the raw sensor force (3,) out of every serialized sample .pt,
  2. summarise the empirical envelope (per-axis + magnitude + direction cone +
     frame-to-frame rate + contact on/off), and
  3. expose is_plausible(force_seq, envelope) so a candidate generated force
     trajectory can be accepted/rejected BEFORE it is ever handed to the FEM.

No GPU and no rendering required; runs anywhere the serialized .pt tiers exist.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
from typing import Optional

import numpy as np
import torch

# id looks like "real_s01_v0000" / "synt_s31_v1715": domain, sequence, frame.
_ID_RE = re.compile(r"^(?P<domain>real|synt)_s(?P<seq>\d+)_v(?P<frame>\d+)$")


def load_forces(
    data_dir: str,
    domains: tuple[str, ...] = ("real",),
    cache: Optional[str] = None,
) -> dict[str, np.ndarray]:
    """Return {sequence_key: (T, 3) float64} forces, frame-ordered per sequence.

    Each batch .pt is a list of {"id", "image", "force"} dicts; we keep only the
    tiny force vectors and the id (the 1.3 GB image tensor is dropped per batch so
    peak memory stays ~one batch). `cache` is a small .npz of the extracted forces:
    reused if present (instant, ~1 MB) so refinements never re-read the 42 GB tiers.
    """
    if cache and os.path.exists(cache):
        z = np.load(cache)
        return {k: z[k] for k in z.files}

    per_seq: dict[str, list[tuple[int, np.ndarray]]] = {}
    batch_paths = sorted(glob.glob(os.path.join(data_dir, "*.pt")))
    if not batch_paths:
        raise FileNotFoundError(f"no .pt batches in {data_dir}")

    for path in batch_paths:
        # weights_only=False: trusted local data that is a list of dicts, not a
        # bare state_dict (torch>=2.6 would otherwise refuse to unpickle it).
        samples = torch.load(path, map_location="cpu", weights_only=False)
        for s in samples:
            m = _ID_RE.match(s["id"])
            if m is None:
                continue
            if m["domain"] not in domains:
                continue
            key = f"{m['domain']}_s{m['seq']}"
            f = s["force"].to(torch.float64).numpy()
            per_seq.setdefault(key, []).append((int(m["frame"]), f))
        del samples  # release the batch (images included) before the next load

    out: dict[str, np.ndarray] = {}
    for key, items in per_seq.items():
        items.sort(key=lambda t: t[0])
        out[key] = np.stack([f for _, f in items], axis=0)
    if cache:
        os.makedirs(os.path.dirname(cache) or ".", exist_ok=True)
        np.savez(cache, **out)
    return out


def _quantiles(x: np.ndarray, qs=(0.0, 0.01, 0.05, 0.5, 0.95, 0.99, 1.0)) -> dict:
    return {f"q{int(q * 100):02d}": float(np.quantile(x, q)) for q in qs}


def compute_envelope(
    forces_by_seq: dict[str, np.ndarray],
    contact_floor: Optional[float] = None,
) -> dict:
    """Summarise the empirical force distribution into a reference envelope.

    `contact_floor` is the absolute magnitude (N) below which a frame counts as
    no/near-zero contact. Pass the literature value (0.5 N — the endoscopic
    minimum used by both the Otsuka porcine-kidney study and the da Vinci
    force-feedback study). If None, falls back to the relative q10 (which makes
    the active-fraction circular — kept only for backward compatibility).
    """
    all_f = np.concatenate(list(forces_by_seq.values()), axis=0)  # (N, 3)
    mag = np.linalg.norm(all_f, axis=1)  # (N,)

    # Direction cone: mean unit direction and the angular spread around it. Only
    # frames above the contact floor carry a meaningful direction (near-zero
    # forces have noise-dominated direction and would inflate the cone).
    if contact_floor is None:
        contact_eps = float(np.quantile(mag, 0.10))
        contact_basis = "q10 (relative — circular, back-compat only)"
    else:
        contact_eps = float(contact_floor)
        contact_basis = f"{contact_floor} N (absolute, literature endoscopic floor)"
    active = mag > max(contact_eps, 1e-9)
    unit = all_f[active] / mag[active, None]
    mean_dir = unit.mean(axis=0)
    mean_dir = mean_dir / (np.linalg.norm(mean_dir) + 1e-12)
    cos = np.clip(unit @ mean_dir, -1.0, 1.0)
    angles_deg = np.degrees(np.arccos(cos))

    # Temporal rate: per-sequence frame-to-frame |delta f|, pooled.
    rates = []
    for f in forces_by_seq.values():
        if len(f) > 1:
            rates.append(np.linalg.norm(np.diff(f, axis=0), axis=1))
    rate = np.concatenate(rates) if rates else np.zeros(1)

    return {
        "n_sequences": len(forces_by_seq),
        "n_frames": int(all_f.shape[0]),
        "units": "raw sensor Newtons (unnormalized)",
        "magnitude": {
            "mean": float(mag.mean()),
            "std": float(mag.std()),
            **_quantiles(mag),
        },
        "per_axis": {
            ax: {"mean": float(all_f[:, i].mean()), "std": float(all_f[:, i].std()),
                 **_quantiles(all_f[:, i])}
            for i, ax in enumerate(("x", "y", "z"))
        },
        "direction": {
            "mean_unit": [float(v) for v in mean_dir],
            "angle_deg_from_mean": _quantiles(angles_deg),
            "cone_half_angle_deg_q95": float(np.quantile(angles_deg, 0.95)),
        },
        "contact": {
            "eps_magnitude": contact_eps,
            "eps_basis": contact_basis,
            "active_fraction": float(active.mean()),
        },
        "rate_per_frame": {
            "mean": float(rate.mean()),
            "std": float(rate.std()),
            **_quantiles(rate),
        },
        "per_sequence_magnitude": {
            k: {"mean": float(np.linalg.norm(v, axis=1).mean()),
                "max": float(np.linalg.norm(v, axis=1).max())}
            for k, v in sorted(forces_by_seq.items())
        },
    }


def is_plausible(
    force_seq: np.ndarray,
    envelope: dict,
    mag_hi_key: str = "q99",
    rate_hi_key: str = "q99",
) -> tuple[bool, list[str]]:
    """Acceptance gate: does a candidate (T, 3) force trajectory respect the
    empirical reference envelope? Returns (accepted, reasons_for_rejection).

    Rejections are conservative and explicit — the whole point is that an
    unmeasurable or out-of-envelope force is REFUSED before it corrupts the FEM.
    """
    reasons: list[str] = []
    f = np.asarray(force_seq, dtype=np.float64)
    if f.ndim != 2 or f.shape[1] != 3:
        return False, [f"shape {f.shape} is not (T, 3)"]
    if not np.all(np.isfinite(f)):
        reasons.append("contains NaN/Inf")

    mag = np.linalg.norm(f, axis=1)
    mag_hi = envelope["magnitude"][mag_hi_key]
    if float(mag.max(initial=0.0)) > mag_hi:
        reasons.append(f"peak |f| {mag.max():.4g} > envelope magnitude.{mag_hi_key} {mag_hi:.4g}")

    if len(f) > 1:
        rate = np.linalg.norm(np.diff(f, axis=0), axis=1)
        rate_hi = envelope["rate_per_frame"][rate_hi_key]
        if float(rate.max(initial=0.0)) > rate_hi:
            reasons.append(f"peak rate {rate.max():.4g} > envelope rate.{rate_hi_key} {rate_hi:.4g}")

    return (len(reasons) == 0), reasons


def _maybe_plot(envelope: dict, forces_by_seq: dict[str, np.ndarray], out_fig: str) -> bool:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return False

    all_f = np.concatenate(list(forces_by_seq.values()), axis=0)
    mag = np.linalg.norm(all_f, axis=1)
    fig, axs = plt.subplots(1, 3, figsize=(15, 4.2), dpi=140)
    axs[0].hist(mag, bins=80, color="#378ADD")
    axs[0].axvline(envelope["magnitude"]["q99"], ls="--", color="#C44E52",
                   label=f"q99={envelope['magnitude']['q99']:.3g}")
    axs[0].set(title="Force magnitude (raw N)", xlabel="|f|", ylabel="count")
    axs[0].legend()
    for i, ax_name in enumerate(("x", "y", "z")):
        axs[1].hist(all_f[:, i], bins=80, alpha=0.5, label=ax_name)
    axs[1].set(title="Per-axis force", xlabel="N")
    axs[1].legend()
    rates = [np.linalg.norm(np.diff(v, axis=0), axis=1)
             for v in forces_by_seq.values() if len(v) > 1]
    axs[2].hist(np.concatenate(rates), bins=80, color="#55A868")
    axs[2].set(title="Frame-to-frame rate |df|", xlabel="N/frame")
    fig.suptitle("Empirical force-reference envelope (twin corpus)")
    fig.tight_layout()
    os.makedirs(os.path.dirname(out_fig), exist_ok=True)
    fig.savefig(out_fig)
    return True


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data-dir", required=True, help="dataset dir holding *.pt batches")
    ap.add_argument("--domains", default="real", help="comma list: real,synt")
    ap.add_argument("--out-json", required=True)
    ap.add_argument("--out-fig", default=None)
    ap.add_argument("--forces-cache", default=None,
                    help=".npz of extracted forces: reused if present (skips the 42 GB read)")
    ap.add_argument("--contact-floor", type=float, default=0.5,
                    help="absolute contact-on magnitude in N (literature endoscopic floor 0.5); "
                         "pass a negative value to fall back to the relative q10")
    args = ap.parse_args()

    domains = tuple(d.strip() for d in args.domains.split(",") if d.strip())
    forces = load_forces(args.data_dir, domains=domains, cache=args.forces_cache)
    floor = None if args.contact_floor < 0 else args.contact_floor
    env = compute_envelope(forces, contact_floor=floor)

    os.makedirs(os.path.dirname(args.out_json), exist_ok=True)
    with open(args.out_json, "w") as fh:
        json.dump(env, fh, indent=2)

    print(f"[force_envelope] {env['n_sequences']} seqs, {env['n_frames']} frames")
    print(f"  |f| mean {env['magnitude']['mean']:.4g}  q99 {env['magnitude']['q99']:.4g}  "
          f"max {env['magnitude']['q100']:.4g}")
    print(f"  direction cone half-angle q95: {env['direction']['cone_half_angle_deg_q95']:.1f} deg")
    print(f"  contact active fraction: {env['contact']['active_fraction']:.2f}")
    print(f"  rate/frame q99: {env['rate_per_frame']['q99']:.4g}")
    print(f"  wrote {args.out_json}")

    if args.out_fig:
        ok = _maybe_plot(env, forces, args.out_fig)
        print(f"  figure: {'wrote ' + args.out_fig if ok else 'SKIPPED (matplotlib unavailable)'}")


if __name__ == "__main__":
    main()
