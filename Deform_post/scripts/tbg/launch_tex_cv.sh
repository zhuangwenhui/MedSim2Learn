#!/bin/bash
# 5-fold c2 litmus on mixed_tex_v1: three Ada lanes (proven 105k
# layout -- lane A folds 0,3 / lane B folds 1,4 / lane C fold 2).
# Between lane launches: memory gate (MemAvailable >= GATE_GB) that
# must hold across a 90s trend window (memory-law: point-in-time gates
# are blind to in-flight build growth). H100 (GPU0) untouched.
set -u
cd /workspace/project/MedSim2Learn/KiDKNet
export CUDA_DEVICE_ORDER=PCI_BUS_ID
# ABSOLUTE paths: run_cv resolves args from its CWD but spawns train
# with the workspace root as CWD, so any relative form breaks one of
# the two resolvers (fold0 fail-fast case). Absolute is anchor-free.
ROOT=/workspace/project/MedSim2Learn
OUT=$ROOT/DataFlow/KiDKNet/outputs/cv5_tex
SPLITS=$ROOT/DataFlow/KiDKNet/splits/cv5_tex
CFG=$ROOT/DataFlow/KiDKNet/configs_tex
LOGDIR=$OUT
GATE_GB=180

mem_gb () { awk '/MemAvailable/ {print int($2/1048576)}' /proc/meminfo; }

wait_gate () {
    while true; do
        m1=$(mem_gb)
        if [ "$m1" -ge "$GATE_GB" ]; then
            sleep 90
            m2=$(mem_gb)
            if [ "$m2" -ge "$GATE_GB" ] && [ "$m2" -ge $((m1 - 15)) ]; then
                echo "[gate] pass: ${m1}G -> ${m2}G"
                return
            fi
        fi
        echo "[gate] hold: ${m1}G available"
        sleep 60
    done
}

lane () {
    local gpu=$1 folds=$2
    CUDA_VISIBLE_DEVICES=$gpu /opt/venv/bin/python scripts/run_cv.py \
        --splits-dir "$SPLITS" --cv-out "$OUT" --config-dir "$CFG" \
        --conditions c2 --folds "$folds" \
        > "$LOGDIR/lane_gpu${gpu}.log" 2>&1
    echo "LANE-EXIT gpu=$gpu folds=$folds rc=$?"
}

mkdir -p "$LOGDIR"
lane 1 0,3 &
P1=$!
wait_gate
lane 2 1,4 &
P2=$!
wait_gate
lane 3 2 &
P3=$!
wait $P1 $P2 $P3
echo "TEXCV-ALL-LANES-EXIT"
