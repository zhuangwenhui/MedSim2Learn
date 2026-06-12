"""Batch driver: run many sequences with throttled process-level parallelism.

Each sequence runs as its own `python main.py run ...` subprocess so Open3D
offscreen rendering and the DeformSim exe stay process-isolated (Open3D
visualizers are not safe to share across threads of one process), each with
its own log under <out_root>/_batch_logs/. A failing sequence is recorded and
the batch continues; per-sequence result rows merge into batch_log.csv at the
end, in the order the caller listed the sequences.
"""

import csv
import json
import os
import subprocess
import sys
import threading
import time


def expand_seq_list(spec):
    """Expand seq tokens and inclusive 'NN..MM' ranges, preserving zero-padding.

    Comma list ('05,06,07') and/or numeric ranges ('05..31'); forms may be
    mixed ('02,05..07,12'). Non-numeric tokens (e.g. synthetic sequence names
    like '01_r3') are accepted verbatim. Duplicates are dropped, first
    occurrence wins.
    """
    out = []
    seen = set()
    for tok in str(spec).split(","):
        t = tok.strip()
        if not t:
            continue
        if ".." in t:
            a_str, _, b_str = t.partition("..")
            a_str, b_str = a_str.strip(), b_str.strip()
            if not (a_str.isdigit() and b_str.isdigit()):
                raise ValueError(f"unrecognized seq range: '{t}' (expected NN..MM)")
            a, b = int(a_str), int(b_str)
            width = max(len(a_str), len(b_str))
            step = 1 if a <= b else -1
            for i in range(a, b + step, step):
                s = str(i).zfill(width)
                if s not in seen:
                    seen.add(s)
                    out.append(s)
        else:
            # Plain token: numeric ('05') or a synthetic sequence name ('01_r3').
            if t not in seen:
                seen.add(t)
                out.append(t)
    if not out:
        raise ValueError(f"seq list expanded to zero sequences: '{spec}'")
    return out


def _run_one(main_py, seq, out_dir, log_path, config_path, keep_intermediate,
             subsample):
    """Run one sequence subprocess; return its result row dict."""
    start = time.time()
    start_iso = time.strftime("%Y-%m-%dT%H:%M:%S")
    cmd = [sys.executable, main_py, "run", "--seq", seq, "--out-dir", out_dir]
    if config_path:
        cmd += ["--config", config_path]
    if keep_intermediate:
        cmd += ["--keep-intermediate"]
    if subsample:
        cmd += ["--subsample", str(subsample)]

    with open(log_path, "w", encoding="utf-8") as log_fh:
        log_fh.write(f"[seq {seq}] START {start_iso}\n")
        log_fh.flush()
        proc = subprocess.run(cmd, stdout=log_fh, stderr=subprocess.STDOUT)

    status = "OK" if proc.returncode == 0 else "FAIL"
    fail_stage = ""
    error = ""
    frame_count = ""
    maxu_max = ""
    kept_mb = ""

    status_path = os.path.join(out_dir, "run_status.json")
    if os.path.isfile(status_path):
        try:
            with open(status_path, "r") as fh:
                st = json.load(fh)
            if status == "FAIL":
                fail_stage = st.get("stage", "")
                error = st.get("error", f"exit code {proc.returncode}")
        except (OSError, json.JSONDecodeError):
            pass
    elif status == "FAIL":
        error = f"exit code {proc.returncode} (no run_status.json)"

    meta_path = os.path.join(out_dir, "replay_meta.json")
    if os.path.isfile(meta_path):
        try:
            with open(meta_path, "r") as fh:
                meta = json.load(fh)
            frame_count = meta.get("frame_count", "")
            maxu_max = meta.get("maxu_max_mm", "")
        except (OSError, json.JSONDecodeError):
            pass

    if os.path.isdir(out_dir):
        total = 0
        for dirpath, _dirnames, filenames in os.walk(out_dir):
            for fname in filenames:
                try:
                    total += os.path.getsize(os.path.join(dirpath, fname))
                except OSError:
                    pass
        kept_mb = round(total / (1024 * 1024), 1)

    wall = round(time.time() - start, 1)
    end_iso = time.strftime("%Y-%m-%dT%H:%M:%S")
    with open(log_path, "a", encoding="utf-8") as log_fh:
        log_fh.write(f"[seq {seq}] END {end_iso}  status={status} wall={wall}s\n")

    return {
        "seq": seq,
        "status": status,
        "start": start_iso,
        "end": end_iso,
        "wall_seconds": wall,
        "frame_count": frame_count,
        "maxu_max_mm": maxu_max,
        "kept_mb": kept_mb,
        "fail_stage": fail_stage,
        "error": error,
    }


def run_batch(main_py, seq_list, out_root, config_path=None, max_parallel=1,
              keep_intermediate=False, subsample=None):
    """Run every sequence in `seq_list`; returns (n_ok, n_fail, batch_log_path)."""
    seqs = expand_seq_list(seq_list)
    os.makedirs(out_root, exist_ok=True)
    logs_dir = os.path.join(out_root, "_batch_logs")
    os.makedirs(logs_dir, exist_ok=True)

    print("=== run batch ===")
    print(f"Sequences:    {len(seqs)}  [{', '.join(seqs)}]")
    print(f"OutRoot:      {out_root}")
    print(f"MaxParallel:  {max_parallel}")
    print(f"KeepInterm.:  {keep_intermediate}")
    print()

    results = {}
    results_lock = threading.Lock()
    sem = threading.Semaphore(max_parallel)
    threads = []
    done_count = [0]
    batch_start = time.time()

    def worker(seq):
        with sem:
            out_dir = os.path.join(out_root, f"seq{seq}")
            log_path = os.path.join(logs_dir, f"seq{seq}.log")
            print(f"[launch] seq {seq}")
            row = _run_one(main_py, seq, out_dir, log_path, config_path,
                           keep_intermediate, subsample)
            with results_lock:
                results[seq] = row
                done_count[0] += 1
                print(f"[done {done_count[0]}/{len(seqs)}] seq {seq}  "
                      f"status={row['status']} wall={row['wall_seconds']}s "
                      f"frames={row['frame_count']} maxu={row['maxu_max_mm']}mm "
                      f"kept={row['kept_mb']}MB")

    for seq in seqs:
        t = threading.Thread(target=worker, args=(seq,), daemon=True)
        t.start()
        threads.append(t)
    for t in threads:
        t.join()

    # Merge per-seq results in the caller's order.
    batch_log = os.path.join(out_root, "batch_log.csv")
    fields = ["seq", "status", "start", "end", "wall_seconds", "frame_count",
              "maxu_max_mm", "kept_mb", "fail_stage", "error"]
    rows = [results.get(seq, {
        "seq": seq, "status": "NO_RESULT", "start": "", "end": "",
        "wall_seconds": "", "frame_count": "", "maxu_max_mm": "", "kept_mb": "",
        "fail_stage": "no_result", "error": "worker produced no result row",
    }) for seq in seqs]
    with open(batch_log, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    n_ok = sum(1 for r in rows if r["status"] == "OK")
    n_fail = len(rows) - n_ok
    print()
    print("=== batch complete ===")
    print(f"Total wall:   {round(time.time() - batch_start, 1)} s")
    print(f"OK / FAIL:    {n_ok} / {n_fail}")
    print(f"batch_log:    {batch_log}")
    print(f"per-seq logs: {logs_dir}")
    if n_fail:
        print("FAILED sequences:")
        for r in rows:
            if r["status"] != "OK":
                print(f"  seq {r['seq']}: [{r['fail_stage']}] {r['error']}")
    return n_ok, n_fail, batch_log


def _self_test():
    """expand_seq_list contract; raises AssertionError on failure."""
    assert expand_seq_list("05,06,07") == ["05", "06", "07"]
    assert expand_seq_list("05..08") == ["05", "06", "07", "08"]
    assert expand_seq_list("02,05..07,12") == ["02", "05", "06", "07", "12"]
    assert expand_seq_list("9..11") == ["09", "10", "11"], "width from widest endpoint"
    assert expand_seq_list("03..01") == ["03", "02", "01"], "descending range"
    assert expand_seq_list("05,05,05") == ["05"], "duplicates dropped"
    assert expand_seq_list("01_r1,01_r2") == ["01_r1", "01_r2"], "synthetic names"
    for bad in ("", "1..x", "a..b"):
        try:
            expand_seq_list(bad)
            raise AssertionError(f"expand_seq_list accepted invalid spec {bad!r}")
        except ValueError:
            pass
    print("simrun.batch self-test PASS")
