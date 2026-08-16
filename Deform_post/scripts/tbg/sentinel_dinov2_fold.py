"""Pre-registered DINOv2 sentinel fold (survey addendum, runs BEFORE
the next 5-fold litmus launch).

Single-variable representation probe under the frozen c2 protocol:
frozen DINOv2 vitb14 CLS features + shallow MLP head, trained on the
SAME fold0 split of mixed_tex_v1 the ConvNeXt 5-fold will use
(synt -> train/val, real -> test). Reports per-axis and pooled MAE /
RMSE on the real test split so the number sits directly next to the
fold's ConvNeXt evaluation_report.

Feature extraction runs once and is cached beside the report. Env:
CUDA_VISIBLE_DEVICES picks the GPU; paths are fixed to the tex round.
"""
import json
import os
import time

import numpy as np
import torch
import torch.nn.functional as F

P = "/workspace/project/MedSim2Learn/DataFlow"
DATA = f"{P}/Deform_post/preprocessed/datasets/mixed_tex_v1"
SPLIT = f"{P}/KiDKNet/splits/cv5_tex/fold0/c2_synt2real_split.json"
OUT = f"{P}/KiDKNet/outputs/sentinel_dinov2_tex_fold0"
DEV = "cuda"
BATCH = 256
IMAGENET_MEAN = torch.tensor([0.485, 0.456, 0.406]).view(1, 3, 1, 1)
IMAGENET_STD = torch.tensor([0.229, 0.224, 0.225]).view(1, 3, 1, 1)
HEAD_EPOCHS = 200
PATIENCE = 20


def load_dataset():
    """Preallocate and fill in place -- stacking 105k f32 images via
    torch.stack would spike ~2x (~165G) during the copy (memory-law
    lesson); the filled tensor itself is ~83G, run in a quiet window.
    """
    idx = json.load(open(f"{DATA}/sequence_index.json"))
    total = idx["total_samples"]
    images = forces = None
    for sid in idx["seq_order"]:
        ent = idx["sequences"][sid]
        batch = torch.load(f"{DATA}/{ent['batch_file']}",
                           map_location="cpu", weights_only=False)
        if images is None:
            shape = batch[0]["image"].shape
            images = torch.empty((total, *shape), dtype=torch.float32)
            forces = torch.empty((total, 3), dtype=torch.float32)
        for k, s in enumerate(batch):
            images[ent["start"] + k] = s["image"]
            forces[ent["start"] + k] = s["force"]
        del batch
    return images, forces


@torch.no_grad()
def extract_features(images):
    cache = f"{OUT}/dinov2_features.pt"
    if os.path.exists(cache):
        return torch.load(cache, map_location="cpu", weights_only=False)
    model = torch.hub.load("facebookresearch/dinov2", "dinov2_vitb14")
    model.eval().to(DEV)
    feats = []
    t0 = time.time()
    for i in range(0, len(images), BATCH):
        x = images[i:i + BATCH].to(DEV)
        x = F.interpolate(x, size=(224, 224), mode="bilinear",
                          align_corners=False)
        x = (x - IMAGENET_MEAN.to(DEV)) / IMAGENET_STD.to(DEV)
        feats.append(model(x).cpu())
        if (i // BATCH) % 40 == 0:
            print(f"features {i}/{len(images)} "
                  f"({time.time() - t0:.0f}s)", flush=True)
    del model
    torch.cuda.empty_cache()
    out = torch.cat(feats)
    torch.save(out, cache)
    return out


class Head(torch.nn.Module):
    def __init__(self, d_in=768):
        super().__init__()
        self.net = torch.nn.Sequential(
            torch.nn.Linear(d_in, 512), torch.nn.GELU(),
            torch.nn.Dropout(0.1),
            torch.nn.Linear(512, 256), torch.nn.GELU(),
            torch.nn.Linear(256, 3))

    def forward(self, x):
        return self.net(x)


def metrics(pred, target):
    err = pred - target
    mag_p, mag_t = pred.norm(dim=1), target.norm(dim=1)
    mag_err = (mag_p - mag_t).abs()
    return {
        # protocol headline: magnitude MAE (matches the c2 baseline's
        # magnitude_mean_absolute_error field verbatim)
        "magnitude_mean_absolute_error": float(mag_err.mean()),
        "magnitude_mean_relative_error": float(
            (mag_err / mag_t.clamp(min=1e-6)).mean()),
        "mae_per_axis": err.abs().mean(dim=0).tolist(),
        "mae": float(err.abs().mean()),
        "rmse_per_axis": err.pow(2).mean(dim=0).sqrt().tolist(),
        "rmse": float(err.pow(2).mean().sqrt()),
        "n": int(len(pred)),
    }


def main():
    os.makedirs(OUT, exist_ok=True)
    split = json.load(open(SPLIT))
    tr = torch.tensor(split["train_indices"])
    va = torch.tensor(split["val_indices"])
    te = torch.tensor(split["test_indices"])
    print(f"split: train={len(tr)} val={len(va)} test={len(te)}",
          flush=True)
    images, forces = load_dataset()
    print(f"dataset: {tuple(images.shape)}", flush=True)
    feats = extract_features(images)
    del images

    f_tr, y_tr = feats[tr].to(DEV), forces[tr].to(DEV)
    f_va, y_va = feats[va].to(DEV), forces[va].to(DEV)
    f_te, y_te = feats[te], forces[te]
    head = Head(feats.shape[1]).to(DEV)
    opt = torch.optim.AdamW(head.parameters(), lr=1e-3,
                            weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(
        opt, T_max=HEAD_EPOCHS)
    best_val, best_state, bad = float("inf"), None, 0
    for ep in range(HEAD_EPOCHS):
        head.train()
        perm = torch.randperm(len(f_tr), device=DEV)
        for i in range(0, len(perm), 4096):
            j = perm[i:i + 4096]
            loss = F.smooth_l1_loss(head(f_tr[j]), y_tr[j])
            opt.zero_grad()
            loss.backward()
            opt.step()
        sched.step()
        head.eval()
        with torch.no_grad():
            val_mae = float((head(f_va) - y_va).abs().mean())
        if val_mae < best_val - 1e-5:
            best_val, bad = val_mae, 0
            best_state = {k: v.detach().clone()
                          for k, v in head.state_dict().items()}
        else:
            bad += 1
            if bad >= PATIENCE:
                print(f"early stop at epoch {ep}", flush=True)
                break
        if ep % 10 == 0:
            print(f"epoch {ep}: val MAE {val_mae:.4f} "
                  f"(best {best_val:.4f})", flush=True)
    head.load_state_dict(best_state)
    head.eval()
    with torch.no_grad():
        preds = torch.cat([
            head(f_te[i:i + 8192].to(DEV)).cpu()
            for i in range(0, len(f_te), 8192)])
    report = {
        "condition": "sentinel_dinov2_vitb14_frozen_mlp_head",
        "data_dir": DATA,
        "split": SPLIT,
        "val_best_mae": best_val,
        "test_real": metrics(preds, y_te),
    }
    torch.save({"pred": preds, "target": y_te},
               f"{OUT}/test_predictions.pt")
    with open(f"{OUT}/sentinel_report.json", "w") as fh:
        json.dump(report, fh, indent=2)
    print("SENTINEL " + json.dumps(report["test_real"]), flush=True)


if __name__ == "__main__":
    main()
