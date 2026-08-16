"""Build datasets/mixed_tex_v1: real half hardlinked from datasets/mixed,
synt half hardlinked from sources/synt/tex-v1 per-seq batches.

Adapted verbatim from sources/synt/dr-c1-v1/_tools/build_mixed_dr.py
(DR-C2-20260811 gates); only source, output and provenance strings
changed. Gates -- any failure exits nonzero and removes the output:
  G1 62 sequences, 31 real_ + 31 synt_ prefixes in seq_order
  G2 per-seq synt sample ids identical (list equality) to mixed's twin half
  G3 index offsets identical to datasets/mixed/sequence_index.json, total 105044
  G4 real half: same inode as datasets/mixed batch (byte identity) + sha256
"""
import hashlib
import json
import os
import shutil
import sys
from datetime import datetime

import torch
import yaml

P = "/workspace/project/MedSim2Learn/DataFlow/Deform_post/preprocessed"
MIXED = f"{P}/datasets/mixed"
TEXSRC = f"{P}/sources/synt/tex-v1"
OUT = f"{P}/datasets/mixed_tex_v1"

fails = []


def gate(ok, msg):
    print(("[PASS] " if ok else "[FAIL] ") + msg, flush=True)
    if not ok:
        fails.append(msg)


def sha256_file(path, chunk=1 << 22):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while block := f.read(chunk):
            h.update(block)
    return h.hexdigest()


idx = json.load(open(f"{MIXED}/sequence_index.json"))
seq_order, seqs = idx["seq_order"], idx["sequences"]
n_real = sum(1 for s in seq_order if s.startswith("real_"))
n_synt = sum(1 for s in seq_order if s.startswith("synt_"))
gate(len(seq_order) == 62 and n_real == 31 and n_synt == 31,
     f"G1 seq_order: {len(seq_order)} seqs, real={n_real} synt={n_synt}")

if os.path.exists(OUT):
    print(f"[ABORT] {OUT} already exists (no-clobber)", flush=True)
    sys.exit(2)
os.makedirs(OUT)

new_index, cursor, real_hashes = {}, 0, {}
for sid in seq_order:
    ent = seqs[sid]
    bf = ent["batch_file"]
    if sid.startswith("real_"):
        src = f"{MIXED}/{bf}"
        os.link(src, f"{OUT}/{bf}")
        h = sha256_file(f"{OUT}/{bf}")
        real_hashes[bf] = h
        gate(os.path.samefile(src, f"{OUT}/{bf}"),
             f"G4 {sid}: inode-identical to mixed ({bf}, sha256 {h[:12]}...)")
        n = ent["n"]
    else:
        nn = sid.replace("synt_seq", "")
        src = (f"{TEXSRC}/seq{nn}/serialized/dataset"
               f"/preprocessed_batch_0000.pt")
        tx = torch.load(src, map_location="cpu", weights_only=False)
        tw = torch.load(f"{MIXED}/{bf}", map_location="cpu",
                        weights_only=False)
        ids_equal = [s["id"] for s in tx] == [s["id"] for s in tw]
        gate(ids_equal and len(tx) == ent["n"],
             f"G2 {sid}: n={len(tx)} vs twin n={ent['n']}, "
             f"ids_equal={ids_equal}")
        os.link(src, f"{OUT}/{bf}")
        n = len(tx)
    new_index[sid] = {"batch_file": bf, "start": cursor,
                      "end": cursor + n, "n": n}
    cursor += n

offsets_ok = all(new_index[s] == seqs[s] for s in seq_order)
gate(offsets_ok and cursor == 105044,
     f"G3 offsets identical={offsets_ok}, total={cursor}")

with open(f"{OUT}/sequence_index.json", "w") as f:
    json.dump({"seq_order": seq_order, "sequences": new_index,
               "total_samples": cursor}, f, indent=2)
with open(f"{MIXED}/metadata.yaml") as f:
    meta = yaml.safe_load(f)
meta["dataset_name"] = "mixed_tex_v1"
meta["creation_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
meta["provenance"] = (
    "real half hardlinked from datasets/mixed; synt half hardlinked "
    "from sources/synt/tex-v1 (T-B-G textured renders, owner-passed "
    "gate 2026-08-16; texture assignment in tex-v1/_meta)")
with open(f"{OUT}/metadata.yaml", "w") as f:
    yaml.safe_dump(meta, f)
with open(f"{OUT}/_real_half_sha256.json", "w") as f:
    json.dump(real_hashes, f, indent=2)

if fails:
    print(f"\nBUILD FAILED: {len(fails)} gate failures -- removing {OUT}",
          flush=True)
    shutil.rmtree(OUT)
    sys.exit(1)
print(f"\nBUILD OK: {OUT} ({cursor} samples, 62 seqs)", flush=True)
