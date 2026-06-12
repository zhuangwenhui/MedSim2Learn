"""Run one DeformSim exact replay as a subprocess.

The exe is configured exclusively through SIM2LEARN_PARAM_* environment
variables and writes its timestamped "DeformedSample_ComplexObject_*" folder
relative to its working directory, so it is launched from inside `sim_dir`.
At runtime the exe only needs the Intel MKL and compiler runtime DLLs on
PATH (the Visual Studio environment that the build scripts import is a
compile-time concern and is not replicated here).
"""

import os
import subprocess


def run_deformsim_replay(exe, mesh_path, annotation_path, sim_dir,
                         force_list_csv, young, poisson, num_threads=1,
                         mkl_threads=1, seed=20260530,
                         mkl_bin=None, compiler_bin=None):
    """Launch the exe in FORCE_LIST_CSV replay mode; return the output PLY dir.

    Raises on a non-zero exit code or when no DeformedSample dir appears.
    The sampling-band variables are intentionally not set: in replay mode the
    exe ignores them, and leaving them unset keeps the env minimal.
    """
    for path, label in ((exe, "exe"), (mesh_path, "mesh"),
                        (annotation_path, "annotation"),
                        (force_list_csv, "force list CSV")):
        if not os.path.isfile(path):
            raise FileNotFoundError(f"{label} not found: {path}")
    os.makedirs(sim_dir, exist_ok=True)

    env = os.environ.copy()
    runtime_dirs = [d for d in (mkl_bin, compiler_bin) if d]
    for d in runtime_dirs:
        if not os.path.isdir(d):
            raise FileNotFoundError(f"runtime DLL directory not found: {d}")
    if runtime_dirs:
        env["PATH"] = ";".join(runtime_dirs) + ";" + env.get("PATH", "")

    env["SIM2LEARN_PARAM_PLY_PATH"] = os.path.abspath(mesh_path)
    env["SIM2LEARN_PARAM_ANNOTATION_PATH"] = os.path.abspath(annotation_path)
    env["SIM2LEARN_PARAM_FORCE_LIST_CSV"] = os.path.abspath(force_list_csv)
    env["SIM2LEARN_PARAM_SEED"] = str(seed)
    env["SIM2LEARN_PARAM_NUM_THREADS"] = str(num_threads)
    env["SIM2LEARN_PARAM_MKL_NUM_THREADS"] = str(mkl_threads)
    env["SIM2LEARN_PARAM_MATERIAL_YOUNG"] = str(young)
    env["SIM2LEARN_PARAM_MATERIAL_POISSON"] = str(poisson)

    before = _deformed_dirs(sim_dir)
    proc = subprocess.run([exe], cwd=sim_dir, env=env)
    print(f"=== DeformSim exit code: {proc.returncode} ===")
    if proc.returncode != 0:
        raise RuntimeError(f"LVBasicFramework.exe exited with code {proc.returncode}")

    new_dirs = sorted(set(_deformed_dirs(sim_dir)) - set(before))
    if new_dirs:
        return os.path.join(sim_dir, new_dirs[-1])
    # Fall back to the newest dir (e.g. when re-running into a pre-populated sim_dir).
    existing = _deformed_dirs(sim_dir)
    if not existing:
        raise RuntimeError(f"no DeformedSample_ComplexObject* dir under {sim_dir}")
    newest = max(existing, key=lambda d: os.path.getmtime(os.path.join(sim_dir, d)))
    return os.path.join(sim_dir, newest)


def _deformed_dirs(sim_dir):
    return [d for d in os.listdir(sim_dir)
            if d.startswith("DeformedSample_ComplexObject")
            and os.path.isdir(os.path.join(sim_dir, d))]
