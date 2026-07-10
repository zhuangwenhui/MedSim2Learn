#!/usr/bin/env bash
# Track B UDA driver: c2 baseline + c2+CORAL over CV folds, one fold per GPU,
# mmap loading (RAM-safe: ~2GB/proc vs ~41GB cached), wandb ONLINE (key bridged from
# the root container's /root/.netrc). --skip-existing makes it resumable: already-complete
# (cond,fold) runs are skipped, so re-invoking completes the set without redoing folds.
#
# Usage: run_coral_cv.sh "<folds>" <coral_weight> "<gpus>"
#   e.g. run_coral_cv.sh "2 3 4" 1.0 "0 1 2"        # complete folds 2,3,4
#        run_coral_cv.sh "0 1 2 3 4" 1.0 "0 1 2 3"  # full 5-fold sweep
set -uo pipefail

FOLDS="${1:-0 1 2 3 4}"
CW="${2:-1.0}"
read -r -a GPUS <<< "${3:-0 1 2 3}"

KID=/home/wenhui/MedSim2Learn/KiDKNet
HS=/home/wenhui/MedSim2Learn/DataFlow/kidknet_host
PY=/home/wenhui/rag_parsers_venv/bin/python
ENT=zwhdiscovery-kyoto-university
CONTAINER=MedSim2Learn_wenhui
cd "$KID"
mkdir -p "$HS/runlogs"

# Bridge the wandb API key from the root container's netrc (never printed).
export WANDB_API_KEY=$(docker exec -u 0 "$CONTAINER" /opt/venv/bin/python -c \
  "import netrc;a=netrc.netrc('/root/.netrc').authenticators('api.wandb.ai');print(a[2] if a else '')" 2>/dev/null)
[ -n "$WANDB_API_KEY" ] || { echo "FATAL: no wandb key from container $CONTAINER"; exit 1; }
export WANDB_SILENT=true PYTHONUNBUFFERED=1 OMP_NUM_THREADS=6 MKL_NUM_THREADS=6
echo "wandb key bridged (len ${#WANDB_API_KEY}); folds='$FOLDS' coral_weight=$CW gpus='${GPUS[*]}'"

run_fold () {  # $1=fold $2=gpu
  local f=$1 g=$2
  CUDA_VISIBLE_DEVICES=$g "$PY" scripts/run_cv.py --conditions c2 --folds "$f" \
    --splits-dir "$HS/splits/cv5" --cv-out "$HS/outputs/cv5_baseline" --config-dir "$HS/configs" \
    --python "$PY" --skip-existing --wandb --wandb-mode online \
    --wandb-project kidknet-trackb-uda --wandb-entity "$ENT" > "$HS/runlogs/base_fold${f}.log" 2>&1
  CUDA_VISIBLE_DEVICES=$g "$PY" scripts/run_cv.py --conditions c2 --folds "$f" --coral-weight "$CW" \
    --splits-dir "$HS/splits/cv5" --cv-out "$HS/outputs/cv5_coral" --config-dir "$HS/configs" \
    --python "$PY" --skip-existing --wandb --wandb-mode online \
    --wandb-project kidknet-trackb-uda --wandb-entity "$ENT" > "$HS/runlogs/coral_fold${f}.log" 2>&1
}

# Round-robin folds to GPUs; each GPU processes its folds SEQUENTIALLY (one training job
# per GPU at a time). Concurrency == number of GPUs.
declare -A GPU_FOLDS
i=0
for f in $FOLDS; do
  g=${GPUS[$(( i % ${#GPUS[@]} ))]}
  GPU_FOLDS[$g]="${GPU_FOLDS[$g]:-} $f"
  i=$((i+1))
done
for g in "${!GPU_FOLDS[@]}"; do
  ( for f in ${GPU_FOLDS[$g]}; do run_fold "$f" "$g"; done ) &
done
wait
echo "DONE folds: $FOLDS"
