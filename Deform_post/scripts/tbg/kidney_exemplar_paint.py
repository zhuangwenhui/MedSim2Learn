"""v4-P: view-space exemplar painting -- continuity-first texture.

Owner verdict on v3 (2026-08-15): atlas-space tiling reads as a quilt,
far from one continuous organ texture. Root causes: tile seams AND uv
chart seams, both artifacts of synthesizing IN atlas space. This arm
paints in VIEW space instead: one real full-FOV kidney region (organ-
level vessel tree intact) is contour-warped onto each orbit view's
silhouette, then progressively splatted to UV exactly like the SD
painter -- so 3D-adjacent surface points receive image-adjacent content
regardless of chart layout. Zero generation, zero tiles; the only seams
left are the 8 view-boundary fringes (blended) and residual warp
distortion.

Post-pass fills unpainted texels by neighbour propagation so bilinear
sampling at chart borders stops bleeding grey padding into renders.

Env: SHEET (warp asset stem, default 01_f0432), OUT_DIR.
"""
import glob
import math
import os

import numpy as np
import torch
import torch.nn.functional as F
import xatlas
from PIL import Image

import kidney_painter as kp
from kidney_painter import (MESH, TEX, depth_control, erode, export_obj,
                            look_at, orbit_eyes, parse_ascii_ply,
                            rasterize, sample_texture, splat_bilinear)

# splat views at 2x: 512-view bilinear splatting into the 1024 atlas
# left a sub-texel weight checkerboard that rendered as a woven moire
kp.RES = 1024
RES = kp.RES
SD_RES = 512  # the SD-1.x refine pass stays at its native resolution

REFINE = os.environ.get("REFINE", "0") == "1"
REFINE_STRENGTH = float(os.environ.get("REFINE_STRENGTH", "0.45"))
LORA_DIR = os.environ.get(
    "LORA_DIR", "/workspace/project/tools/kidney_assets/lora_out_v4")

DEV = "cuda"
N_BINS = 144  # 72 produced visible chevron interpolation artifacts
SHEET = os.environ.get("SHEET", "01_f0432")
ASSETS = "/workspace/project/tools/kidney_assets/native_corpus_v1/warp_assets"
CORPUS = "/workspace/project/tools/kidney_assets/lora_train_v4"
_DEFAULT_OUT = ("arm6_hybrid" if REFINE else "arm5_viewpaint")
OUT = os.environ.get(
    "OUT_DIR", f"/workspace/project/tools/kidney_pilot_out/{_DEFAULT_OUT}")
ERODE_IT = 4


def build_refine_pipe(use_lora=True):
    """Depth-ControlNet inpaint pipeline, LoRA optional.

    use_lora=False exists because the v4 LoRA is glare-poisoned (its
    corpus bakes specular sheets into "material"); the plain SD prior
    is the control for albedo-flavoured prompting.
    """
    import torch as _torch
    from diffusers import (ControlNetModel,
                           StableDiffusionControlNetInpaintPipeline)
    cn = ControlNetModel.from_pretrained(kp.CONTROL,
                                         torch_dtype=_torch.float16)
    pipe = StableDiffusionControlNetInpaintPipeline.from_pretrained(
        kp.BASE, controlnet=cn, torch_dtype=_torch.float16,
        safety_checker=None).to(DEV)
    if use_lora:
        pipe.load_lora_weights(LORA_DIR)
    print(f"refine pipe ready, lora={LORA_DIR if use_lora else 'OFF'}",
          flush=True)
    return pipe


def refine_view(pipe, gen, init, region, ctrl, strength,
                prompt=None, negative=None):
    """Low-strength SD pass: keeps the init layout, authors material.

    Runs at SD_RES and is upsampled back -- SD-1.x degrades off 512.
    """
    init_pil = Image.fromarray(
        (init.cpu().numpy() * 255).astype("uint8")).resize(
            (SD_RES, SD_RES), Image.LANCZOS)
    mask_pil = Image.fromarray(
        (region.float().cpu().numpy() * 255).astype("uint8")).resize(
            (SD_RES, SD_RES), Image.NEAREST)
    ctrl_small = ctrl.resize((SD_RES, SD_RES), Image.LANCZOS)
    out = pipe(prompt or kp.PROMPT_ARM3, image=init_pil,
               mask_image=mask_pil, control_image=ctrl_small,
               negative_prompt=negative or kp.NEGATIVE,
               num_inference_steps=30, strength=strength,
               generator=gen).images[0]
    arr = np.asarray(out.resize((RES, RES), Image.LANCZOS))
    return torch.from_numpy(arr).float().to(DEV) / 255.0


def box_blur(x, k=31, it=3):
    pad = k // 2
    y = x.unsqueeze(0).unsqueeze(0)
    for _ in range(it):
        y = F.avg_pool2d(y, k, stride=1, padding=pad,
                         count_include_pad=False)
    return y[0, 0]


def flatten_luminance(rgb, mask):
    """Divide out the low-frequency baked shading inside the mask.

    Gain clamp tightened after round 1: (0.6, 1.8) over-brightened the
    crevice zones into a washed-out pallor.
    """
    lum = rgb.mean(dim=2)
    m = mask.float()
    field = box_blur(lum * m) / box_blur(m).clamp(min=1e-4)
    target = lum[mask].mean()
    gain = (target / field.clamp(min=1e-4)).clamp(0.78, 1.35)
    return (rgb * gain.unsqueeze(2)).clamp(0, 1)


def match_corpus_colour(rgb, mask):
    """Per-channel mean/std alignment to the curated-crop statistics.

    Round 1 read pale next to real frames; this pins the sheet's global
    colour cast to the corpus it must blend with. Robust std via IQR.
    """
    files = sorted(glob.glob(f"{CORPUS}/*.png"))[::12][:64]
    ref = np.stack([np.asarray(Image.open(f).convert("RGB"),
                               dtype=np.float32) / 255.0 for f in files])
    ref = ref.reshape(-1, 3)
    src = rgb[mask].cpu().numpy()

    def stats(a):
        q1, q2, q3 = np.percentile(a, (25, 50, 75), axis=0)
        return q2, (q3 - q1) / 1.349

    ref_mu, ref_sd = stats(ref)
    src_mu, src_sd = stats(src)
    gain = np.clip(ref_sd / np.maximum(src_sd, 1e-4), 0.6, 1.6)
    out = rgb.clone()
    for c in range(3):
        out[..., c] = (rgb[..., c] - float(src_mu[c])) * float(gain[c]) \
            + float(ref_mu[c])
    return out.clamp(0, 1)


def radial_lookup(table, theta):
    """Linear interpolation into a circular radius table.

    Bin count is taken from the table itself -- the sheet tables come
    from the Windows-side segmenter and may use a different resolution
    than the silhouette tables built here (72 vs 144 desync caused a
    CUDA index-out-of-bounds in round 2).
    """
    n = table.shape[0]
    pos = (theta + math.pi) / (2 * math.pi) * n
    b0 = pos.floor().long() % n
    b1 = (b0 + 1) % n
    frac = (pos - pos.floor())
    return table[b0] * (1 - frac) + table[b1] * frac


def silhouette_table(mask):
    ys, xs = torch.nonzero(mask, as_tuple=True)
    cy, cx = ys.float().mean(), xs.float().mean()
    ang = torch.atan2(ys.float() - cy, xs.float() - cx)
    rad = torch.hypot(ys.float() - cy, xs.float() - cx)
    bins = (((ang + math.pi) / (2 * math.pi) * N_BINS).long()) % N_BINS
    table = torch.zeros(N_BINS, device=mask.device)
    for b in range(N_BINS):
        sel = rad[bins == b]
        if len(sel):
            table[b] = torch.quantile(sel, 0.98)
    for b in torch.nonzero(table == 0).flatten().tolist():
        table[b] = max(table[(b - 1) % N_BINS], table[(b + 1) % N_BINS])
    sm = table.clone()
    for b in range(N_BINS):
        sm[b] = (table[(b - 1) % N_BINS] + 2 * table[b]
                 + table[(b + 1) % N_BINS]) / 4
    return (cx, cy), sm


def warp_view(mask, sheet_rgb, sheet_mask, sheet_c, sheet_table):
    """Map each silhouette pixel to the sheet via polar correspondence."""
    (cx, cy), sil_table = silhouette_table(mask)
    ys, xs = torch.nonzero(mask, as_tuple=True)
    theta = torch.atan2(ys.float() - cy, xs.float() - cx)
    rho = torch.hypot(ys.float() - cy, xs.float() - cx)
    # 0.88 keeps the warp off the sheet's outermost band -- the pale
    # fascia/glare ring that painted every silhouette rim grey-green
    rho_frac = (rho / radial_lookup(sil_table, theta).clamp(min=1.0)
                ).clamp(0, 0.88)
    r_sheet = radial_lookup(sheet_table, theta)
    sx = sheet_c[0] + torch.cos(theta) * rho_frac * r_sheet
    sy = sheet_c[1] + torch.sin(theta) * rho_frac * r_sheet
    h, w = sheet_mask.shape
    # shrink toward the sheet centroid until the sample lands on tissue
    inside = sheet_mask[sy.long().clamp(0, h - 1),
                        sx.long().clamp(0, w - 1)]
    for shrink in (0.85, 0.7):
        if bool(inside.all()):
            break
        bad = ~inside
        sx[bad] = sheet_c[0] + torch.cos(theta[bad]) * rho_frac[bad] \
            * r_sheet[bad] * shrink
        sy[bad] = sheet_c[1] + torch.sin(theta[bad]) * rho_frac[bad] \
            * r_sheet[bad] * shrink
        inside = sheet_mask[sy.long().clamp(0, h - 1),
                            sx.long().clamp(0, w - 1)]
    grid = torch.stack([sx / (w - 1) * 2 - 1, sy / (h - 1) * 2 - 1],
                       dim=1).view(1, 1, -1, 2)
    samp = F.grid_sample(sheet_rgb.permute(2, 0, 1).unsqueeze(0), grid,
                         mode="bilinear", align_corners=True)
    view = torch.full((RES, RES, 3), 0.5, device=DEV)
    view[ys, xs] = samp[0, :, 0, :].T
    return view


def fill_unpainted(texture, painted):
    """Propagate painted colours into unpainted texels (chart padding)."""
    tex = texture.permute(2, 0, 1).unsqueeze(0)
    m = painted.float().view(1, 1, TEX, TEX)
    for _ in range(48):
        if bool((m > 0).all()):
            break
        tex_new = F.avg_pool2d(tex * m, 3, stride=1, padding=1) \
            / F.avg_pool2d(m, 3, stride=1, padding=1).clamp(min=1e-6)
        grow = (F.max_pool2d(m, 3, stride=1, padding=1) > 0) & (m == 0)
        tex = torch.where(grow.expand_as(tex), tex_new, tex)
        m = (m + grow.float()).clamp(max=1)
    return tex[0].permute(1, 2, 0).clamp(0, 1)


def main():
    os.makedirs(OUT, exist_ok=True)
    data = np.load(f"{ASSETS}/{SHEET}.npz")
    sheet_rgb = torch.from_numpy(data["rgb"]).float().to(DEV) / 255.0
    sheet_mask = torch.from_numpy(data["mask"]).to(DEV)
    sheet_c = data["centroid"].tolist()
    sheet_table = torch.from_numpy(data["radial"]).to(DEV)
    sheet_rgb = flatten_luminance(sheet_rgb, sheet_mask)
    sheet_rgb = match_corpus_colour(sheet_rgb, sheet_mask)
    Image.fromarray((sheet_rgb.cpu().numpy() * 255).astype("uint8")).save(
        f"{OUT}/sheet_flattened.png")

    v_np, f_np = parse_ascii_ply(MESH)
    v_np -= v_np.mean(axis=0)
    v_np /= np.abs(v_np).max()
    vmap, indices, uvs = xatlas.parametrize(v_np, f_np.astype(np.uint32))
    v_np, uv_np, f_np = (v_np[vmap], uvs.astype(np.float32),
                         indices.astype(np.int64))
    print(f"arm5 mesh: {len(v_np)} verts sheet={SHEET}", flush=True)
    verts = torch.from_numpy(v_np).to(DEV)
    uv = torch.from_numpy(uv_np).to(DEV)
    faces = torch.from_numpy(f_np).to(DEV)

    tex_acc = torch.zeros(TEX, TEX, 3, device=DEV)
    w_acc = torch.zeros(TEX, TEX, 1, device=DEV)
    views = []
    pipe = build_refine_pipe() if REFINE else None
    gen = torch.Generator(DEV).manual_seed(20260815) if REFINE else None
    # two polar coverage views: the 8-view orbit (elev +20/-10) leaves
    # steep top/bottom surface unseen, and those charts were filled by
    # atlas-space propagation -- rendering as pale straight-edged decals
    eyes = orbit_eyes(2.6) + [[0.9, 2.4, 0.2], [0.9, -2.2, 0.4]]
    for k, eye in enumerate(eyes):
        rot, eye_t = look_at(eye)
        uv_map, z_map, facing, mask = rasterize(verts, faces, uv, rot,
                                                eye_t)
        mask = erode(mask, ERODE_IT)
        view = warp_view(mask, sheet_rgb, sheet_mask, sheet_c, sheet_table)
        # a texel only counts as covered above a MEANINGFUL weight;
        # grazing-angle first claims (facing^2 ~ 2.5e-3) must stay
        # overwritable by a later frontal view, or steep faces keep
        # smeared rim content forever
        painted_uv = (w_acc[..., 0] > 0.05)
        cov = sample_texture(painted_uv.float().unsqueeze(-1).expand(
            TEX, TEX, 3), uv_map)[..., 0] > 0.5
        new_region = mask & ~cov
        blend_region = mask & cov
        if REFINE:
            texture_now = (tex_acc / w_acc.clamp(min=1e-6)).clamp(0, 1)
            init = view.clone()
            if k > 0:
                cur = sample_texture(texture_now, uv_map)
                init[blend_region] = cur[blend_region]
            refine_region = mask if k == 0 else new_region
            ctrl = depth_control(z_map, mask)
            view = refine_view(pipe, gen, init, refine_region, ctrl,
                               REFINE_STRENGTH)
        for region, wgt in ((new_region, 1.0), (blend_region, 0.15)):
            if int(region.sum()) == 0:
                continue
            facing_w = facing[region].clamp(min=0.05).pow(2).unsqueeze(1)
            splat_bilinear(tex_acc, w_acc, uv_map[region] * (TEX - 1),
                           view[region], facing_w * wgt)
        views.append((eye, view))
        print(f"view {k}: new={int(new_region.sum())}px "
              f"blend={int(blend_region.sum())}px", flush=True)

    texture = (tex_acc / w_acc.clamp(min=1e-6)).clamp(0, 1)
    texture = fill_unpainted(texture, w_acc[..., 0] > 1e-4)
    Image.fromarray((texture.cpu().numpy() * 255).astype("uint8")).save(
        f"{OUT}/texture_atlas.png")
    export_obj(f"{OUT}/kidney_textured.obj", v_np, uv_np, f_np,
               "kidney_textured")
    rows = []
    for eye, view in views:
        rot, eye_t = look_at(eye)
        uv_map, _, _, mask = rasterize(verts, faces, uv, rot, eye_t)
        samp = sample_texture(texture, uv_map)
        samp[~mask] = 1.0
        rows.append(np.concatenate(
            [(view.cpu().numpy() * 255).astype("uint8"),
             (samp.cpu().numpy() * 255).astype("uint8")], 1))
    if len(rows) % 2:
        rows.append(np.full_like(rows[0], 255))
    grid = [np.concatenate(rows[i:i + 2], 1)
            for i in range(0, len(rows), 2)]
    Image.fromarray(np.concatenate(grid, 0)).save(
        f"{OUT}/kidney_arm5_montage.png")
    print("ARM5-VIEWPAINT DONE", flush=True)


if __name__ == "__main__":
    main()
