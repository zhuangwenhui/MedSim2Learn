#!/bin/bash
# T-B-G texture pool: 31 textures (one per production sequence), split
# across 3 Ada GPUs. Each texture: its own canvas (base_canvas_kNN) and
# generator seed (2000+k), matte no-LoRA config frozen from the
# owner-passed sample (STRENGTH 0.6, density gate in the script).
# Writes kidney_pilot_out/texpool_v1/tex_kNN/.
set -u
cd /workspace/project/tools
export CUDA_DEVICE_ORDER=PCI_BUS_ID
CANVAS_DIR=/workspace/project/tools/kidney_assets/native_corpus_v1/base_canvas
POOL_OUT=/workspace/project/tools/kidney_pilot_out/texpool_v1
mkdir -p "$POOL_OUT"
run_lane () {
    local gpu=$1; shift
    for k in "$@"; do
        kk=$(printf "%02d" "$k")
        USE_LORA=0 STRENGTH=0.6 SEED=$((2000 + k)) \
        CANVAS="$CANVAS_DIR/base_canvas_k$kk.png" \
        OUT_DIR="$POOL_OUT/tex_k$kk" \
        CUDA_VISIBLE_DEVICES=$gpu venvs/tex/bin/python \
            kidney_basegen_paint.py > "$POOL_OUT/tex_k$kk.log" 2>&1 \
            || echo "TEX-FAIL k=$kk" >> "$POOL_OUT/failures.txt"
    done
}
run_lane 1 $(seq 0 10) &
P1=$!
run_lane 2 $(seq 11 20) &
P2=$!
run_lane 3 $(seq 21 30) &
P3=$!
wait $P1 $P2 $P3
ls -d "$POOL_OUT"/tex_k*/ | wc -l
cat "$POOL_OUT/failures.txt" 2>/dev/null
echo "TEXPOOL-EXIT"
