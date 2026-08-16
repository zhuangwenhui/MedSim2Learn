"""Kidney-mesh texture painter v2 -- progressive inpainting edition.

Owner gate feedback (2026-08-15): texture/material still far from the
real frames. v2 addresses the diagnosed sources: (1) progressive
view-by-view INPAINTING -- later views project the already-painted
texture and only fill uncovered regions, so detail is preserved instead
of averaged away; (2) bilinear splatting with facing-angle weights
replaces nearest-neighbour (kills the moire net); (3) depth-map edge
ring removed via mask erosion + percentile normalization (kills the
magenta outline); (4) IP-Adapter scale raised, multi-reference attempted
with single-ref fallback. The unlit re-render column remains a DEBUG
view; the production comparison happens through the Open3D renderer
(textured .obj exported for that step).
"""
import math
import os

import numpy as np
import torch
import torch.nn.functional as F
import xatlas
from PIL import Image

import kaolin as kal
from diffusers import ControlNetModel, StableDiffusionControlNetInpaintPipeline

DEV = "cuda"
RES, TEX = 512, 1024
N_VIEWS = 8
BASE = "CompVis/stable-diffusion-v1-4"
CONTROL = "lllyasviel/control_v11f1p_sd15_depth"
PROMPT = ("laparoscopic close-up of a living human kidney surface, "
          "glistening pale pink tissue, dense fine branching blood "
          "vessels, wet specular sheen, endoscope lighting, photorealistic")
NEGATIVE = ("cartoon, painting, illustration, text, watermark, blurry, "
            "flat, outline, border, hole, cavity")
MESH = "/workspace/project/tools/kidney_assets/kidney_rest_seq01.ply"
ARM = os.environ.get("ARM", "arm2")
LORA_DIR = os.environ.get(
    "LORA_DIR", "/workspace/project/tools/kidney_assets/lora_out")
# arm3 uses the exact LoRA training caption so inference matches the
# learned distribution; other arms keep the hand-written prompt.
PROMPT_ARM3 = "a photo of sks kidney surface, laparoscopic view"
REF_DIR = "/workspace/project/tools/kidney_assets/real_refs"
IP_SCALE = float(os.environ.get("IP_SCALE", "0.8"))
OUT = f"/workspace/project/tools/kidney_pilot_out/{ARM}_v2"
ERODE = 4


def parse_ascii_ply(path):
    with open(path) as fh:
        lines = fh.read().splitlines()
    n_v = n_f = body = 0
    for i, ln in enumerate(lines):
        if ln.startswith("element vertex"):
            n_v = int(ln.split()[-1])
        elif ln.startswith("element face"):
            n_f = int(ln.split()[-1])
        elif ln.startswith("end_header"):
            body = i + 1
            break
    verts = np.array([[float(x) for x in ln.split()[:3]]
                      for ln in lines[body:body + n_v]], dtype=np.float32)
    faces = np.array([[int(x) for x in ln.split()[1:4]]
                      for ln in lines[body + n_v:body + n_v + n_f]],
                     dtype=np.int64)
    return verts, faces


def look_at(eye):
    eye = torch.tensor(eye, dtype=torch.float32, device=DEV)
    fwd = -eye / eye.norm()
    right = torch.linalg.cross(fwd, torch.tensor([0.0, 1.0, 0.0], device=DEV))
    right = right / (right.norm() + 1e-8)
    up = torch.linalg.cross(right, fwd)
    return torch.stack([right, up, fwd]), eye


def rasterize(verts, faces, uv, rot, eye, focal=2.4):
    cam = (verts - eye) @ rot.T
    dist = cam[:, 2].clamp(min=1e-4)
    ndc = focal * cam[:, :2] / dist.unsqueeze(1)
    z_k = -dist  # kaolin DIB-R: camera looks down -z, larger z = nearer
    fv_img = ndc[faces].unsqueeze(0)
    fv_z = z_k[faces].unsqueeze(0)
    v0, v1, v2 = (verts[faces[:, k]] for k in range(3))
    n = torch.linalg.cross(v1 - v0, v2 - v0)
    n = n / (n.norm(dim=1, keepdim=True) + 1e-8)
    n_cam_z = -(n @ rot.T)[:, 2]
    facing_feat = n_cam_z.unsqueeze(-1).expand(-1, 3).unsqueeze(-1)
    feats = torch.cat([uv[faces], z_k[faces].unsqueeze(-1), facing_feat],
                      -1).unsqueeze(0)
    interp, mask, _ = kal.render.mesh.dibr_rasterization(
        RES, RES, fv_z, fv_img, feats, n_cam_z.unsqueeze(0))
    return (interp[0, ..., :2], interp[0, ..., 2], interp[0, ..., 3],
            mask[0] > 0.5)


def erode(mask, it):
    m = mask.float().unsqueeze(0).unsqueeze(0)
    for _ in range(it):
        m = -F.max_pool2d(-m, 3, stride=1, padding=1)
    return m[0, 0] > 0.5


def depth_control(z_map, mask):
    inv = torch.zeros_like(z_map)
    zin = z_map[mask]
    lo, hi = torch.quantile(zin, 0.02), torch.quantile(zin, 0.98)
    inv[mask] = ((z_map[mask] - lo) / (hi - lo + 1e-6)).clamp(0, 1)
    img = (inv * 255).byte().cpu().numpy()
    return Image.fromarray(np.stack([img] * 3, -1))


def splat_bilinear(tex_acc, w_acc, uv_pix, rgb, weight):
    x = uv_pix[:, 0].clamp(0, TEX - 1 - 1e-4)
    y = uv_pix[:, 1].clamp(0, TEX - 1 - 1e-4)
    x0, y0 = x.floor().long(), y.floor().long()
    fx, fy = (x - x0.float()).unsqueeze(1), (y - y0.float()).unsqueeze(1)
    for dx, dy, w in ((0, 0, (1 - fx) * (1 - fy)), (1, 0, fx * (1 - fy)),
                      (0, 1, (1 - fx) * fy), (1, 1, fx * fy)):
        idx = ((y0 + dy).clamp(max=TEX - 1), (x0 + dx).clamp(max=TEX - 1))
        ww = w * weight
        tex_acc.index_put_(idx, rgb * ww, accumulate=True)
        w_acc.index_put_(idx, ww, accumulate=True)


def orbit_eyes(radius):
    eyes = []
    for k in range(N_VIEWS):
        ang = 2 * math.pi * k / N_VIEWS
        elev = math.radians(20.0 if k % 2 == 0 else -10.0)
        eyes.append([radius * math.cos(elev) * math.cos(ang),
                     radius * math.sin(elev),
                     radius * math.cos(elev) * math.sin(ang)])
    return eyes


def sample_texture(texture, uv_map):
    grid = uv_map * 2 - 1
    return F.grid_sample(texture.permute(2, 0, 1).unsqueeze(0),
                         grid.unsqueeze(0), mode="bilinear",
                         align_corners=False)[0].permute(1, 2, 0)


def export_obj(path, verts, uv, faces, tex_name):
    with open(path, "w") as fh:
        fh.write(f"mtllib {tex_name}.mtl\nusemtl textured\n")
        for v in verts:
            fh.write(f"v {v[0]:.6f} {v[1]:.6f} {v[2]:.6f}\n")
        for t in uv:
            fh.write(f"vt {t[0]:.6f} {1.0 - t[1]:.6f}\n")
        for f0, f1, f2 in faces + 1:
            fh.write(f"f {f0}/{f0} {f1}/{f1} {f2}/{f2}\n")
    with open(f"{os.path.splitext(path)[0]}.mtl", "w") as fh:
        fh.write("newmtl textured\nmap_Kd texture_atlas.png\n")


def main():
    os.makedirs(OUT, exist_ok=True)
    v_np, f_np = parse_ascii_ply(MESH)
    v_np -= v_np.mean(axis=0)
    v_np /= np.abs(v_np).max()
    vmap, indices, uvs = xatlas.parametrize(v_np, f_np.astype(np.uint32))
    v_np, uv_np, f_np = v_np[vmap], uvs.astype(np.float32), indices.astype(np.int64)
    print(f"v2 mesh: {len(v_np)} verts, {len(f_np)} faces, arm={ARM}", flush=True)
    verts = torch.from_numpy(v_np).to(DEV)
    uv = torch.from_numpy(uv_np).to(DEV)
    faces = torch.from_numpy(f_np).to(DEV)

    cn = ControlNetModel.from_pretrained(CONTROL, torch_dtype=torch.float16)
    pipe = StableDiffusionControlNetInpaintPipeline.from_pretrained(
        BASE, controlnet=cn, torch_dtype=torch.float16,
        safety_checker=None).to(DEV)
    ip_kwargs = {}
    prompt = PROMPT
    if ARM == "arm3":
        pipe.load_lora_weights(LORA_DIR)
        prompt = PROMPT_ARM3
        single_ref = None
        print(f"arm3: LoRA loaded from {LORA_DIR}", flush=True)
    elif ARM == "arm2":
        pipe.load_ip_adapter("h94/IP-Adapter", subfolder="models",
                             weight_name="ip-adapter_sd15.bin")
        pipe.set_ip_adapter_scale(IP_SCALE)
        refs = sorted(os.listdir(REF_DIR))[:3]
        imgs = [Image.open(f"{REF_DIR}/{r}").convert("RGB") for r in refs]
        # multi-image form for a single adapter; the first pipe() call
        # falls back to single-ref at runtime if this form is unsupported
        ip_kwargs["ip_adapter_image"] = [imgs]
        single_ref = imgs[0]
        print(f"arm2 v2: multi-ref IP x{len(imgs)}, scale={IP_SCALE}",
              flush=True)
    else:
        single_ref = None

    gen = torch.Generator(DEV).manual_seed(20260815)
    tex_acc = torch.zeros(TEX, TEX, 3, device=DEV)
    w_acc = torch.zeros(TEX, TEX, 1, device=DEV)
    views = []
    for k, eye in enumerate(orbit_eyes(2.6)):
        rot, eye_t = look_at(eye)
        uv_map, z_map, facing, mask = rasterize(verts, faces, uv, rot, eye_t)
        mask = erode(mask, ERODE)
        ctrl = depth_control(z_map, mask)
        texture = (tex_acc / w_acc.clamp(min=1e-6)).clamp(0, 1)
        painted_uv = (w_acc[..., 0] > 1e-4)
        cur = sample_texture(texture, uv_map)
        cov = sample_texture(painted_uv.float().unsqueeze(-1).expand(
            TEX, TEX, 3), uv_map)[..., 0] > 0.5
        init = torch.full((RES, RES, 3), 0.5, device=DEV)
        init[mask & cov] = cur[mask & cov]
        inpaint = (mask & ~cov) | ~mask
        init_pil = Image.fromarray(
            (init.cpu().numpy() * 255).astype("uint8"))
        mask_pil = Image.fromarray(
            (inpaint.float().cpu().numpy() * 255).astype("uint8"))
        def run_view():
            return pipe(prompt, image=init_pil, mask_image=mask_pil,
                        control_image=ctrl, negative_prompt=NEGATIVE,
                        num_inference_steps=30, strength=1.0,
                        generator=gen, **ip_kwargs).images[0]

        try:
            img = run_view()
        except (TypeError, ValueError):
            if "ip_adapter_image" not in ip_kwargs:
                raise
            ip_kwargs["ip_adapter_image"] = single_ref
            print("multi-ref unsupported -- single-ref fallback", flush=True)
            img = run_view()
        views.append((eye, ctrl, img))
        rgb = torch.from_numpy(np.asarray(
            img.resize((RES, RES)))).float().to(DEV) / 255.0
        new_region = mask & ~cov
        blend_region = mask & cov
        for region, wgt in ((new_region, 1.0), (blend_region, 0.15)):
            if int(region.sum()) == 0:
                continue
            facing_w = facing[region].clamp(min=0.05).pow(2).unsqueeze(1)
            splat_bilinear(tex_acc, w_acc, uv_map[region] * (TEX - 1),
                           rgb[region], facing_w * wgt)
        print(f"view {k}: new={int(new_region.sum())}px "
              f"blend={int(blend_region.sum())}px", flush=True)

    texture = (tex_acc / w_acc.clamp(min=1e-6)).clamp(0, 1)
    Image.fromarray((texture.cpu().numpy() * 255).astype("uint8")).save(
        f"{OUT}/texture_atlas.png")
    export_obj(f"{OUT}/kidney_textured.obj", v_np, uv_np, f_np, "kidney_textured")
    rows = []
    for eye, ctrl, img in views:
        rot, eye_t = look_at(eye)
        uv_map, _, _, mask = rasterize(verts, faces, uv, rot, eye_t)
        samp = sample_texture(texture, uv_map)
        samp[~mask] = 1.0
        rows.append(np.concatenate(
            [np.asarray(ctrl), np.asarray(img.resize((RES, RES))),
             (samp.cpu().numpy() * 255).astype("uint8")], 1))
    Image.fromarray(np.concatenate(rows, 0)).save(
        f"{OUT}/kidney_{ARM}_v2_montage.png")
    print("KIDNEY-PAINTER-V2 DONE", flush=True)


if __name__ == "__main__":
    main()
