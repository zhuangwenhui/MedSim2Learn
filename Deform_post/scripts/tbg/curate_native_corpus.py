"""Purify the native-res tissue corpus (v4 chain, server-side).

Reproduces the v3 three-stage curation on native_corpus_v1/crops, saved
as a file this time so the chain is re-runnable:
  1. DINOv2 vitb14 (torch hub, original publisher) CLS features ->
     k-NN density ranking; the dense cluster is the organ-surface mode,
     instrument crops sit in the sparse tail.
  2. CLIP zero-shot instrument scrub (openai/clip-vit-base-patch32,
     safetensors per CVE-2025-32434), two rounds at 0.35 then 0.22.
  3. Contact sheet + manifest for human final inspection.

Env: /workspace/project/tools/venvs/tex. GPU via CUDA_VISIBLE_DEVICES.
"""
import csv
import glob
import os

import numpy as np
import torch
from PIL import Image

BASE = "/workspace/project/tools/kidney_assets/native_corpus_v1"
OUT = f"{BASE}/curated"
DENSITY_KEEP = 1300
KNN = 20
CLIP_ROUNDS = (0.35, 0.22)
DEV = "cuda"
IMAGENET_MEAN = torch.tensor([0.485, 0.456, 0.406]).view(3, 1, 1)
IMAGENET_STD = torch.tensor([0.229, 0.224, 0.225]).view(3, 1, 1)


def load_batch(paths, size):
    ims = []
    for p in paths:
        im = Image.open(p).convert("RGB").resize((size, size), Image.LANCZOS)
        t = torch.from_numpy(np.asarray(im)).permute(2, 0, 1).float() / 255.0
        ims.append((t - IMAGENET_MEAN) / IMAGENET_STD)
    return torch.stack(ims).to(DEV)


@torch.no_grad()
def dinov2_features(files):
    model = torch.hub.load("facebookresearch/dinov2", "dinov2_vitb14")
    model.eval().to(DEV)
    feats = []
    for i in range(0, len(files), 64):
        feats.append(model(load_batch(files[i:i + 64], 224)).cpu())
    del model
    torch.cuda.empty_cache()
    f = torch.cat(feats)
    return torch.nn.functional.normalize(f, dim=1)


@torch.no_grad()
def clip_instrument_probs(files):
    from transformers import CLIPModel, CLIPProcessor
    name = "openai/clip-vit-base-patch32"
    model = CLIPModel.from_pretrained(name, use_safetensors=True).to(DEV)
    proc = CLIPProcessor.from_pretrained(name)
    texts = ["a photo of a metal surgical instrument or forceps",
             "a photo of smooth wet kidney tissue surface"]
    probs = []
    for i in range(0, len(files), 64):
        ims = [Image.open(p).convert("RGB") for p in files[i:i + 64]]
        inputs = proc(text=texts, images=ims, return_tensors="pt",
                      padding=True).to(DEV)
        logits = model(**inputs).logits_per_image
        probs.append(logits.softmax(dim=1)[:, 0].cpu())
    del model
    torch.cuda.empty_cache()
    return torch.cat(probs)


def contact_sheet(files, path, thumb=108, cols=20):
    rng = np.random.default_rng(20260815)
    sample = sorted(rng.choice(len(files), min(300, len(files)),
                               replace=False).tolist())
    n_rows = (len(sample) + cols - 1) // cols
    grid = Image.new("RGB", (cols * thumb, n_rows * thumb))
    for k, j in enumerate(sample):
        im = Image.open(files[j]).convert("RGB").resize((thumb, thumb),
                                                        Image.LANCZOS)
        grid.paste(im, ((k % cols) * thumb, (k // cols) * thumb))
    grid.save(path)


def main():
    os.makedirs(OUT, exist_ok=True)
    files = sorted(glob.glob(f"{BASE}/crops/*.png"))
    print(f"crops: {len(files)}", flush=True)

    feats = dinov2_features(files)
    sim = feats @ feats.T
    knn_density = sim.topk(KNN + 1, dim=1).values[:, 1:].mean(dim=1)
    order = knn_density.argsort(descending=True)
    dense_idx = set(order[:DENSITY_KEEP].tolist())
    stage1 = [f for j, f in enumerate(files) if j in dense_idx]
    print(f"stage1 dense cluster: {len(stage1)}", flush=True)

    kept = stage1
    for rnd, thr in enumerate(CLIP_ROUNDS, 1):
        p = clip_instrument_probs(kept)
        kept = [f for f, pi in zip(kept, p.tolist()) if pi <= thr]
        print(f"stage2 round {rnd} (thr {thr}): {len(kept)}", flush=True)

    dens = {f: float(knn_density[j]) for j, f in enumerate(files)}
    with open(f"{OUT}/curated_manifest.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["file", "density"])
        for f in kept:
            w.writerow([os.path.basename(f), f"{dens[f]:.4f}"])
    with open(f"{OUT}/curated_files.txt", "w") as fh:
        fh.write("\n".join(os.path.basename(f) for f in kept) + "\n")
    contact_sheet(kept, f"{OUT}/curated_contact.png")
    print(f"FINAL curated: {len(kept)} -> {OUT}", flush=True)


if __name__ == "__main__":
    main()
