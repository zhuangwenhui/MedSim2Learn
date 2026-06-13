"""Per-sequence QA artifacts from a completed replay directory.

Reads <seq_dir>/labels.csv + png/ + sim/DeformedSample_*/ and writes
maxu.csv, force_waveform.png, twin_sync.mp4, montage.png, rest_vs_peak.png,
folding the max|u| summary stats into replay_meta.json so they survive PLY
deletion.
"""

import csv
import glob
import json
import os

import numpy as np
import open3d as o3d

from .config import DEFAULT_FPS, DEFAULT_POISSON, DEFAULT_YOUNG_MPA
from .meshio import load_mesh

# Kidney rest thickness used for the %thickness annotation. Fixed organ
# geometry, not a per-sequence quantity.
THICKNESS_MM = 52.0


def _find_sim_ply_dir(seq_dir):
    """Return the latest DeformedSample_ComplexObject* dir under <seq_dir>/sim."""
    cands = sorted(glob.glob(os.path.join(seq_dir, "sim", "DeformedSample_ComplexObject*")))
    if not cands:
        raise FileNotFoundError(
            f"no sim/DeformedSample_ComplexObject* dir under {seq_dir}")
    return cands[-1]


def _load_labels(labels_csv):
    """Load labels.csv -> (sample_ids list, F array (N,3), |F| array (N,)).

    labels.csv is the REAL sensor force in Newtons (the supervision target),
    in frame order; SampleID == PLY stem == PNG stem.
    """
    sids, F = [], []
    with open(labels_csv, "r", newline="") as fh:
        rd = csv.DictReader(fh)
        for row in rd:
            sids.append(row["SampleID"])
            F.append([float(row["force_x"]), float(row["force_y"]), float(row["force_z"])])
    if not sids:
        raise ValueError(f"no rows in {labels_csv}")
    F = np.asarray(F, float)
    return sids, F, np.linalg.norm(F, axis=1)


def compute_maxu(seq_dir, mesh_path, sample_ids):
    """Per-frame max|u| (mm) = max vertex |deformed - rest| over all frames.

    Loads each deformed PLY once (in `sample_ids` order, which is frame order),
    subtracts the rest mesh vertices, and takes the max L2 displacement.
    Returns a float array (N,). Raises on vertex-count mismatch so a corrupt
    PLY set is caught rather than silently mis-paired.
    """
    rest = np.asarray(load_mesh(mesh_path).vertices, float)
    nrest = len(rest)
    ply_dir = _find_sim_ply_dir(seq_dir)
    maxu = np.empty(len(sample_ids), float)
    for k, sid in enumerate(sample_ids):
        ply = os.path.join(ply_dir, sid + ".ply")
        v = np.asarray(o3d.io.read_triangle_mesh(ply).vertices, float)
        if len(v) != nrest:
            raise ValueError(
                f"vertex count mismatch in {sid}.ply: {len(v)} != rest {nrest}")
        maxu[k] = float(np.linalg.norm(v - rest, axis=1).max())
    return maxu


def _save_maxu_csv(seq_dir, maxu):
    """Persist per-frame max|u| to <seq_dir>/maxu.csv (frame_index,max_u_mm)."""
    path = os.path.join(seq_dir, "maxu.csv")
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["frame_index", "max_u_mm"])
        for i, mu in enumerate(maxu):
            w.writerow([i, f"{mu:.6f}"])
    return path


def _update_meta_maxu(seq_dir, maxu, fmag):
    """Fold max|u| summary stats into replay_meta.json so they survive PLY deletion.

    Adds maxu_max_mm, maxu_at_frame, maxu_pearson_vs_F. Returns the loaded meta
    dict (with seq_id/seed/young/poisson/fps for downstream labelling).
    """
    meta_path = os.path.join(seq_dir, "replay_meta.json")
    with open(meta_path, "r") as fh:
        meta = json.load(fh)
    at = int(np.argmax(maxu))
    if len(maxu) >= 2 and np.std(fmag) > 0 and np.std(maxu) > 0:
        pearson = float(np.corrcoef(fmag, maxu)[0, 1])
    else:
        pearson = float("nan")
    meta["maxu_max_mm"] = round(float(maxu[at]), 6)
    meta["maxu_at_frame"] = at
    meta["maxu_pearson_vs_F"] = None if np.isnan(pearson) else round(pearson, 6)
    with open(meta_path, "w") as fh:
        json.dump(meta, fh, indent=2)
    return meta


def _waveform_png(seq_dir, fmag, F, maxu, meta, fps):
    """Write <seq_dir>/force_waveform.png: |F|+max|u| twin axes (top), components (bottom)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    n = len(fmag)
    t = np.arange(n) / float(fps)
    peak_i = int(np.argmax(fmag))
    seq_id = meta.get("seq_id", "?")
    seed = int(meta.get("seed", -1))
    young = meta.get("young_mpa", DEFAULT_YOUNG_MPA)
    poisson = meta.get("poisson", DEFAULT_POISSON)
    pearson = meta.get("maxu_pearson_vs_F")

    fig, (ax_top, ax_bot) = plt.subplots(2, 1, figsize=(11.0, 7.0), dpi=110)
    fig.suptitle(
        f"Twin temporal correspondence  seq {seq_id}  "
        f"N={n} frames @ {fps:g} fps  E={young:g} v={poisson:g}  "
        f"contact seed {seed}"
        + (f"  (|F| vs max|u| Pearson r={pearson:.4f})" if pearson is not None else ""),
        fontsize=10)

    # Top: |F|(t) and max|u|(t) on twin y-axes.
    l1, = ax_top.plot(t, fmag, color="tab:blue", lw=0.8, label="|F| (N)")
    ax_top.set_xlabel("time (s)")
    ax_top.set_ylabel("|F| (N)", color="tab:blue")
    ax_top.tick_params(axis="y", labelcolor="tab:blue")
    ax_top.set_xlim(t[0], t[-1])
    ax_u = ax_top.twinx()
    l2, = ax_u.plot(t, maxu, color="tab:red", lw=0.8, label="max|u| (mm)")
    ax_u.set_ylabel("max|u| (mm)", color="tab:red")
    ax_u.tick_params(axis="y", labelcolor="tab:red")
    ax_top.axvline(t[peak_i], color="k", ls="--", lw=0.7)
    ax_top.legend(handles=[l1, l2], loc="upper left", fontsize=8)
    txt = (f"peak |F| @ frame {peak_i} (t={t[peak_i]:.2f}s)\n"
           f"|F|={fmag[peak_i]:.4f} N   max|u|={maxu[peak_i]:.3f} mm "
           f"({maxu[peak_i] / THICKNESS_MM * 100:.1f}% thick)")
    ax_top.text(0.5, 0.97, txt, transform=ax_top.transAxes, fontsize=8,
                va="top", ha="center",
                bbox=dict(boxstyle="round", fc="white", ec="0.6", alpha=0.85))

    # Bottom: directional components Fx/Fy/Fz.
    ax_bot.set_title("Directional force components", fontsize=9)
    ax_bot.plot(t, F[:, 0], color="tab:red", lw=0.7, label="Fx")
    ax_bot.plot(t, F[:, 1], color="tab:green", lw=0.7, label="Fy")
    ax_bot.plot(t, F[:, 2], color="tab:orange", lw=0.7, label="Fz")
    ax_bot.set_xlabel("time (s)")
    ax_bot.set_ylabel("force component (N)")
    ax_bot.set_xlim(t[0], t[-1])
    ax_bot.legend(loc="upper left", ncol=3, fontsize=8)

    fig.tight_layout(rect=(0, 0, 1, 0.96))
    path = os.path.join(seq_dir, "force_waveform.png")
    fig.savefig(path)
    plt.close(fig)
    return path


def _render_plot_background(fmag, F, maxu, meta, fps, plot_size):
    """Pre-render the static force plot once -> (rgb_uint8, cursor_x_per_frame, ax_data).

    The expensive matplotlib draw happens a single time; per-frame we only blit a
    vertical cursor + text, which is what makes the video writer fast.
    Returns the background RGB image (H, W, 3), an (N,) array of cursor pixel-x
    positions (one per frame), and the (top, bottom) pixel span for the cursor.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_agg import FigureCanvasAgg

    pw, ph = plot_size
    n = len(fmag)
    t = np.arange(n) / float(fps)
    seq_id = meta.get("seq_id", "?")
    seed = int(meta.get("seed", -1))
    young = meta.get("young_mpa", DEFAULT_YOUNG_MPA)
    poisson = meta.get("poisson", DEFAULT_POISSON)

    dpi = 100.0
    fig = plt.figure(figsize=(pw / dpi, ph / dpi), dpi=dpi)
    ax = fig.add_axes((0.10, 0.12, 0.78, 0.78))
    ax.set_title(f"seq {seq_id}  |F|(t) & max|u|(t)  E={young:g}MPa v={poisson:g} seed{seed}",
                 fontsize=9)
    l1, = ax.plot(t, fmag, color="tab:blue", lw=0.8, label="|F| (N)")
    ax.set_xlabel("time (s)")
    ax.set_ylabel("|F| (N)", color="tab:blue")
    ax.tick_params(axis="y", labelcolor="tab:blue")
    ax.set_xlim(t[0], t[-1])
    ax_u = ax.twinx()
    l2, = ax_u.plot(t, maxu, color="tab:red", lw=0.8, label="max|u| (mm)")
    ax_u.set_ylabel("max|u| (mm)", color="tab:red")
    ax_u.tick_params(axis="y", labelcolor="tab:red")
    ax.legend(handles=[l1, l2], loc="upper right", fontsize=7)
    ax.grid(True, alpha=0.25)

    canvas = FigureCanvasAgg(fig)
    canvas.draw()
    buf = np.asarray(canvas.buffer_rgba())[:, :, :3].copy()  # (H, W, 3) uint8 RGB

    # Map each frame's time to a pixel x in the rendered figure using the axes
    # transform, so the cursor lands exactly on the curve regardless of margins.
    fig_h = buf.shape[0]
    xs = np.empty(n, float)
    for i in range(n):
        px, _py = ax.transData.transform((t[i], 0.0))
        xs[i] = px
    # Axes vertical span in pixel coords (top/bottom), y-flip from mpl to image.
    (x0, y0) = ax.transAxes.transform((0, 0))
    (x1, y1) = ax.transAxes.transform((1, 1))
    cursor_top = int(round(fig_h - y1))
    cursor_bot = int(round(fig_h - y0))
    plt.close(fig)
    return buf, xs, (cursor_top, cursor_bot)


def _twin_sync_mp4(seq_dir, fmag, F, maxu, meta, fps, sample_ids):
    """Write <seq_dir>/twin_sync.mp4: side-by-side render | force-cursor plot.

    Left = the rendered PNG for the frame; right = the pre-rendered static force
    plot with a moving vertical cursor and a live text overlay. cv2 'mp4v' at
    `fps`. Returns (path, n_frames_written).
    """
    import cv2

    png_dir = os.path.join(seq_dir, "png")
    n = len(sample_ids)

    # Probe the first render to fix the panel height; force a square left panel.
    first_png = os.path.join(png_dir, sample_ids[0] + ".png")
    img0 = cv2.imread(first_png)
    if img0 is None:
        raise FileNotFoundError(f"cannot read render PNG {first_png}")
    panel = 560  # left/right panel height (and left width), matches proven layout
    plot_w = 620
    plot_size = (plot_w, panel)

    bg, cursor_x, (cur_top, cur_bot) = _render_plot_background(
        fmag, F, maxu, meta, fps, plot_size)
    # bg is RGB; cv2 wants BGR.
    bg_bgr = cv2.cvtColor(bg, cv2.COLOR_RGB2BGR)
    bg_h, bg_w = bg_bgr.shape[:2]

    total_w = panel + bg_w
    total_h = max(panel, bg_h)
    out_path = os.path.join(seq_dir, "twin_sync.mp4")
    fourcc = cv2.VideoWriter.fourcc(*"mp4v")
    vw = cv2.VideoWriter(out_path, fourcc, float(fps), (total_w, total_h))
    if not vw.isOpened():
        raise RuntimeError(f"cv2 VideoWriter failed to open {out_path}")

    t = np.arange(n) / float(fps)
    font = cv2.FONT_HERSHEY_SIMPLEX
    n_written = 0
    try:
        for i, sid in enumerate(sample_ids):
            frame = np.zeros((total_h, total_w, 3), np.uint8)
            # Left: render, resized to the square panel.
            render = cv2.imread(os.path.join(png_dir, sid + ".png"))
            if render is None:
                # Skip a missing render rather than abort the whole video.
                continue
            render = cv2.resize(render, (panel, panel))
            frame[0:panel, 0:panel] = render
            # Right: static plot background + moving cursor (blit only).
            plot = bg_bgr.copy()
            cx = int(round(cursor_x[i]))
            cx = max(0, min(bg_w - 1, cx))
            cv2.line(plot, (cx, cur_top), (cx, cur_bot), (0, 0, 0), 1)
            frame[0:bg_h, panel:panel + bg_w] = plot
            # Live text overlay (top-left of the plot panel).
            fx, fy, fz = F[i]
            lines = [
                f"Frame {i:5d}/{n}",
                f"t   = {t[i]:7.3f} s",
                f"Fx  = {fx:+.4f}",
                f"Fy  = {fy:+.4f}",
                f"Fz  = {fz:+.4f}",
                f"|F| = {fmag[i]:.4f} N",
                f"max|u|= {maxu[i]:.3f} mm",
            ]
            ty = 20
            for ln in lines:
                cv2.putText(frame, ln, (panel + 8, ty), font, 0.42,
                            (0, 0, 0), 1, cv2.LINE_AA)
                ty += 16
            vw.write(frame)
            n_written += 1
    finally:
        vw.release()
    return out_path, n_written


def _label_tile(png_path, lines, scale=1.0):
    """Open a render PNG and burn yellow-on-black label lines (PIL)."""
    from PIL import Image, ImageDraw, ImageFont
    im = Image.open(png_path).convert("RGB")
    d = ImageDraw.Draw(im)
    fs = int(26 * scale)
    try:
        font = ImageFont.truetype("arial.ttf", fs)
    except Exception:
        font = ImageFont.load_default()
    y = 6
    for ln in lines:
        d.rectangle([4, y, 4 + int(0.55 * fs) * len(ln), y + fs + 6], fill=(0, 0, 0))
        d.text((8, y + 2), ln, fill=(255, 255, 0), font=font)
        y += fs + 10
    return im


def _montage(imgs, cols, pad=6):
    """Lay out PIL images in a grid on a white canvas."""
    from PIL import Image
    cw = max(i.width for i in imgs)
    ch = max(i.height for i in imgs)
    rows = (len(imgs) + cols - 1) // cols
    cv = Image.new("RGB", (cols * cw + (cols + 1) * pad, rows * ch + (rows + 1) * pad),
                   (255, 255, 255))
    for k, im in enumerate(imgs):
        r, c = divmod(k, cols)
        cv.paste(im, (pad + c * (cw + pad), pad + r * (ch + pad)))
    return cv


def _montage_pngs(seq_dir, fmag, maxu, sample_ids):
    """Write montage.png (8 frames spanning |F|) and rest_vs_peak.png."""
    png_dir = os.path.join(seq_dir, "png")
    order = np.argsort(fmag)  # ascending |F|
    n = len(order)

    def tile(idx, extra=None):
        sid = sample_ids[idx]
        lines = [f"|F|={fmag[idx]:.2f} N",
                 f"max|u|={maxu[idx]:.2f} mm ({maxu[idx] / THICKNESS_MM * 100:.1f}%)"]
        if extra:
            lines = [extra] + lines
        return _label_tile(os.path.join(png_dir, sid + ".png"), lines)

    pick = np.linspace(0, n - 1, 8).round().astype(int)
    mont = _montage([tile(int(order[k])) for k in pick], cols=4)
    montage_path = os.path.join(seq_dir, "montage.png")
    mont.save(montage_path)

    rest_idx = int(order[0])
    peak_idx = int(order[-1])
    rvp = _montage([tile(rest_idx, extra="REST (min |F|)"),
                    tile(peak_idx, extra="PEAK (max |F|)")], cols=2, pad=10)
    rvp_path = os.path.join(seq_dir, "rest_vs_peak.png")
    rvp.save(rvp_path)
    return montage_path, rvp_path


def artifacts(seq_dir, mesh_path, fps=DEFAULT_FPS, seq_id=None):
    """Produce all per-sequence visual artifacts from a completed replay dir.

    Reads <seq_dir>/labels.csv + png/ + sim/DeformedSample_*/ and writes:
      maxu.csv, force_waveform.png, twin_sync.mp4, montage.png, rest_vs_peak.png.
    Also folds max|u| summary stats into replay_meta.json so they survive PLY
    deletion. max|u| is computed once and reused across every artifact.
    """
    labels_csv = os.path.join(seq_dir, "labels.csv")
    sample_ids, F, fmag = _load_labels(labels_csv)

    # Compute per-frame max|u| ONCE (loads each deformed PLY a single time).
    maxu = compute_maxu(seq_dir, mesh_path, sample_ids)
    maxu_csv = _save_maxu_csv(seq_dir, maxu)
    meta = _update_meta_maxu(seq_dir, maxu, fmag)
    if seq_id is not None:
        meta = dict(meta)
        meta["seq_id"] = seq_id

    wf = _waveform_png(seq_dir, fmag, F, maxu, meta, fps)
    mp4, n_vid = _twin_sync_mp4(seq_dir, fmag, F, maxu, meta, fps, sample_ids)
    montage_path, rvp_path = _montage_pngs(seq_dir, fmag, maxu, sample_ids)

    at = int(np.argmax(maxu))
    print(f"artifacts: seq={meta.get('seq_id')} frames={len(sample_ids)} fps={fps:g}")
    print(f"  maxu max = {maxu[at]:.3f} mm @ frame {at} "
          f"({maxu[at] / THICKNESS_MM * 100:.1f}% thickness)  -> {maxu_csv}")
    print(f"  force_waveform.png -> {wf}")
    print(f"  twin_sync.mp4 ({n_vid} frames) -> {mp4}")
    print(f"  montage.png        -> {montage_path}")
    print(f"  rest_vs_peak.png   -> {rvp_path}")
    return {
        "frames": len(sample_ids),
        "maxu_max_mm": float(maxu[at]),
        "maxu_at_frame": at,
        "video_frames": n_vid,
        "waveform": wf,
        "video": mp4,
        "montage": montage_path,
        "rest_vs_peak": rvp_path,
        "maxu_csv": maxu_csv,
    }


def _self_test():
    """max|u| + artifact outputs on a tiny synthetic sequence; raises on failure."""
    import tempfile

    from .forces import sample_id

    with tempfile.TemporaryDirectory() as td:
        seq = os.path.join(td, "seqXX")
        png_dir = os.path.join(seq, "png")
        sim_dir = os.path.join(seq, "sim", "DeformedSample_ComplexObject_test")
        os.makedirs(png_dir)
        os.makedirs(sim_dir)
        # Rest mesh (the artifacts code subtracts these vertices).
        rest = o3d.geometry.TriangleMesh.create_sphere(radius=10.0, resolution=8)
        rest.compute_vertex_normals()
        rest_ply = os.path.join(seq, "rest.ply")
        o3d.io.write_triangle_mesh(rest_ply, rest)
        rest_v = np.asarray(rest.vertices)

        # 5 frames; known max|u| = frame_index in +z so argmax is the last frame.
        nfr = 5
        seed = 7
        sids = [sample_id(seed, i) for i in range(nfr)]
        for i, sid in enumerate(sids):
            dm = o3d.geometry.TriangleMesh(rest)
            dv = rest_v.copy()
            dv[:, 2] += float(i)  # uniform +z shift => max|u| == i
            dm.vertices = o3d.utility.Vector3dVector(dv)
            o3d.io.write_triangle_mesh(os.path.join(sim_dir, sid + ".ply"), dm)
            # Small white PNG stand-in so montage/video have a render to open.
            o3d.io.write_image(os.path.join(png_dir, sid + ".png"),
                               o3d.geometry.Image(np.full((8, 8, 3), 255, np.uint8)))
        # labels.csv: |F| increasing so peak == last frame too.
        with open(os.path.join(seq, "labels.csv"), "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["SampleID", "force_x", "force_y", "force_z"])
            for i, sid in enumerate(sids):
                w.writerow([sid, f"{0.1 * (i + 1):.6f}", "0", "0"])
        # minimal replay_meta.json (artifacts updates it in place).
        with open(os.path.join(seq, "replay_meta.json"), "w") as fh:
            json.dump({"seq_id": "XX", "seed": seed, "young_mpa": 0.03,
                       "poisson": 0.49, "fps": 30.0}, fh)

        mu = compute_maxu(seq, rest_ply, sids)
        assert np.allclose(mu, np.arange(nfr), atol=1e-6), "compute_maxu values"
        res = artifacts(seq, rest_ply, fps=30.0)
        assert res["maxu_at_frame"] == nfr - 1, "maxu_at_frame != last"
        for name in ("maxu.csv", "force_waveform.png", "twin_sync.mp4",
                     "montage.png", "rest_vs_peak.png"):
            assert os.path.isfile(os.path.join(seq, name)), f"artifact missing: {name}"
        # maxu.csv round-trips and replay_meta.json gained the summary fields.
        mu_rows = []
        with open(os.path.join(seq, "maxu.csv")) as fh:
            rd = csv.DictReader(fh)
            for row in rd:
                mu_rows.append(float(row["max_u_mm"]))
        assert len(mu_rows) == nfr, "maxu.csv rowcount"
        with open(os.path.join(seq, "replay_meta.json")) as fh:
            meta_after = json.load(fh)
        assert abs(meta_after["maxu_max_mm"] - (nfr - 1)) < 1e-6, "meta maxu_max_mm"
        assert meta_after["maxu_at_frame"] == nfr - 1, "meta maxu_at_frame"
        assert "maxu_pearson_vs_F" in meta_after, "meta maxu_pearson_vs_F"
    print("artifacts self-test PASS")
