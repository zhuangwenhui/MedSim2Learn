"""Owner-ruled T-B-G pipeline stage 3: vessels ON the sampled base.

Order ruled 2026-08-15: organ-proper base colour sampling -> base
canvas -> diffusion authors a self-consistent, continuous, natural
vessel network on that canvas -> UV onto the mesh -> lighting and
multi-view rendering only at the classical render stage. Executed
per-view so the vessel network is continuous ON THE SURFACE (a flat
atlas-space generation would be cut at every uv chart border): each
view's init is the rendered base canvas (plus already-painted regions
projected), the depth-ControlNet inpaint pass draws vessels, and the
result is progressively splatted back to UV. Unpainted texels fall
back to the canvas itself.

v4-H lesson applied: the negative prompt carries explicit instrument
terms; strength is an env knob (owner gate compares variants).

Env: CANVAS (atlas png), STRENGTH, OUT_DIR, LORA_DIR via the refine
module. One sample only -- batch production stays behind the owner
gate.
"""
import os

import numpy as np
import torch
import xatlas
from PIL import Image

import kidney_painter as kp
import kidney_exemplar_paint as xp
from kidney_painter import (MESH, TEX, depth_control, erode, export_obj,
                            look_at, orbit_eyes, parse_ascii_ply,
                            rasterize, sample_texture, splat_bilinear)

DEV = "cuda"
RES = kp.RES  # 1024 splat views (set by the refine module import)
CANVAS = os.environ.get(
    "CANVAS", "/workspace/project/tools/kidney_assets/native_corpus_v1"
              "/base_canvas/base_canvas.png")
STRENGTH = float(os.environ.get("STRENGTH", "0.6"))
SEED = int(os.environ.get("SEED", "20260815"))
OUT = os.environ.get(
    "OUT_DIR", "/workspace/project/tools/kidney_pilot_out/arm7_basegen")
USE_LORA = os.environ.get("USE_LORA", "1") == "1"
# albedo-flavoured prompt for the no-LoRA control: the corpus-trained
# LoRA paints baked specular sheets as material (glass/porcelain look).
# "seamless texture" wording caused fabric-like weave zones -- dropped.
PROMPT_MATTE = ("close-up photograph of a smooth pink kidney organ "
                "surface covered by a dense fine branching network of "
                "thin dark red blood vessels, matte wet tissue, flat "
                "even diffuse lighting, no highlights")
PROMPT = PROMPT_MATTE if not USE_LORA else None
NEGATIVE_EXT = (kp.NEGATIVE + ", metal, surgical instrument, forceps, "
                "clamp, scissors, tool, tube, gauze, specular, glossy, "
                "shiny, highlight, reflection, glass, porcelain, "
                "crystal, 3d render, wrinkles, fabric, cloth, "
                "fingerprint, cracks, dry skin, fur")
VESSEL_MIN_FRAC = 0.012   # per-view density gate on authored vessels
VESSEL_TRIES = 3
ERODE_IT = 4


def vessel_fraction(view, region):
    """Fraction of authored pixels clearly darker than the local base."""
    gray = view.mean(dim=2)
    sel = gray[region]
    if sel.numel() == 0:
        return 1.0
    return float((sel < 0.85 * sel.mean()).float().mean())


def main():
    os.makedirs(OUT, exist_ok=True)
    canvas = torch.from_numpy(np.asarray(
        Image.open(CANVAS).convert("RGB"), dtype=np.float32) / 255.0
    ).to(DEV)
    v_np, f_np = parse_ascii_ply(MESH)
    v_np -= v_np.mean(axis=0)
    v_np /= np.abs(v_np).max()
    vmap, indices, uvs = xatlas.parametrize(v_np, f_np.astype(np.uint32))
    v_np, uv_np, f_np = (v_np[vmap], uvs.astype(np.float32),
                         indices.astype(np.int64))
    print(f"arm7 mesh: {len(v_np)} verts strength={STRENGTH}", flush=True)
    verts = torch.from_numpy(v_np).to(DEV)
    uv = torch.from_numpy(uv_np).to(DEV)
    faces = torch.from_numpy(f_np).to(DEV)

    pipe = xp.build_refine_pipe(use_lora=USE_LORA)
    gen = torch.Generator(DEV).manual_seed(SEED)
    tex_acc = torch.zeros(TEX, TEX, 3, device=DEV)
    w_acc = torch.zeros(TEX, TEX, 1, device=DEV)
    views = []
    eyes = orbit_eyes(2.6) + [[0.9, 2.4, 0.2], [0.9, -2.2, 0.4]]
    for k, eye in enumerate(eyes):
        rot, eye_t = look_at(eye)
        uv_map, z_map, facing, mask = rasterize(verts, faces, uv, rot,
                                                eye_t)
        mask = erode(mask, ERODE_IT)
        base_view = sample_texture(canvas, uv_map)
        base_view[~mask] = 0.5
        painted_uv = (w_acc[..., 0] > 0.05)
        cov = sample_texture(painted_uv.float().unsqueeze(-1).expand(
            TEX, TEX, 3), uv_map)[..., 0] > 0.5
        new_region = mask & ~cov
        blend_region = mask & cov
        init = base_view.clone()
        if k > 0:
            texture_now = (tex_acc / w_acc.clamp(min=1e-6)).clamp(0, 1)
            cur = sample_texture(texture_now, uv_map)
            init[blend_region] = cur[blend_region]
        refine_region = mask if k == 0 else new_region
        ctrl = depth_control(z_map, mask)
        for attempt in range(VESSEL_TRIES):
            view = xp.refine_view(pipe, gen, init, refine_region, ctrl,
                                  STRENGTH, prompt=PROMPT,
                                  negative=NEGATIVE_EXT)
            vf = vessel_fraction(view, refine_region)
            if vf >= VESSEL_MIN_FRAC:
                break
            print(f"view {k}: vessel frac {vf:.4f} < "
                  f"{VESSEL_MIN_FRAC} -- resample {attempt + 1}",
                  flush=True)
        for region, wgt in ((new_region, 1.0), (blend_region, 0.15)):
            if int(region.sum()) == 0:
                continue
            facing_w = facing[region].clamp(min=0.05).pow(2).unsqueeze(1)
            splat_bilinear(tex_acc, w_acc, uv_map[region] * (TEX - 1),
                           view[region], facing_w * wgt)
        views.append((eye, view))
        print(f"view {k}: new={int(new_region.sum())}px "
              f"blend={int(blend_region.sum())}px", flush=True)

    painted = w_acc[..., 0] > 1e-4
    texture = (tex_acc / w_acc.clamp(min=1e-6)).clamp(0, 1)
    texture[~painted] = canvas[~painted]
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
        f"{OUT}/kidney_arm7_montage.png")
    print("ARM7-BASEGEN DONE", flush=True)


if __name__ == "__main__":
    main()
