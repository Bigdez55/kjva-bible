#!/usr/bin/env bash
# run_train.sh — build (if needed) and run a TokenlessLM training command in Docker.
#
# Usage:
#   training/docker/run_train.sh smoke                 # 300-iter CPU smoke pretrain
#   training/docker/run_train.sh full                  # 5000-iter pretrain (CPU local / GPU cloud)
#   training/docker/run_train.sh exec <cmd...>         # arbitrary command in the container
#
# Env knobs: TORCH_VARIANT=cpu|cu121  MEM_LIMIT=12g  CPUS=6  GPU=1 (adds --gpus all)
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE="docker compose -f ${HERE}/docker-compose.yml"
CORPUS="corpus/eng_kjv_apocrypha_v1/corpus.txt"
GPU_FLAG=""
[ "${GPU:-0}" = "1" ] && GPU_FLAG="--gpus all"

cmd="${1:-smoke}"; shift || true
case "$cmd" in
  smoke)
    set -x
    $COMPOSE run --rm $GPU_FLAG train python pt/train_byte.py \
      --run-id byte_smoke --corpus "$CORPUS" --iters 300 --batch 8 --seq-len 512 \
      --warmup 30 --eval-every 100 --save-every 300 --no-bench --device auto ;;
  full)
    set -x
    $COMPOSE run --rm $GPU_FLAG train python pt/train_byte.py \
      --run-id byte_v1_20m --corpus "$CORPUS" --iters 5000 --batch 8 --seq-len 1024 \
      --device auto ;;
  exec)
    set -x
    $COMPOSE run --rm $GPU_FLAG train "$@" ;;
  *)
    echo "unknown command: $cmd (use: smoke | full | exec <cmd...>)" >&2; exit 2 ;;
esac
