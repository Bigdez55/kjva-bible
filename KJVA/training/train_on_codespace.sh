#!/usr/bin/env bash
# train_on_codespace.sh — train the neutral byte base in a GitHub Codespace (CPU).
# Zero burden on your Mac; ~30-60 min full run on a 16-core machine.
#
# Usage (from a Codespace terminal):
#   bash "models v7/training/train_on_codespace.sh" smoke   # 300 iters, ~5 min (proof)
#   bash "models v7/training/train_on_codespace.sh" full    # 5000 iters → val_ppl ≤ 3.21
#   bash "models v7/training/train_on_codespace.sh" 2000    # custom iter count
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"   # models v7/training
cd "$HERE"
export TOKENLESS_HOME="$HERE"
export OMP_NUM_THREADS="$(nproc 2>/dev/null || echo 8)"

MODE="${1:-full}"
case "$MODE" in
  smoke) ITERS=300;  SEQ=512;;
  full)  ITERS=5000; SEQ=1024;;
  *)     ITERS="$MODE"; SEQ=1024;;   # numeric → custom iters
esac

# Corpus is committed in the repo (no symlink needed in a fresh clone).
CORPUS="../../ml-training/corpus/eng_kjv_apocrypha_v1/corpus.txt"
[ -f "$CORPUS" ] || { echo "corpus not found at $CORPUS (run from the repo clone)"; exit 1; }

echo "══ Codespace training: $ITERS iters · seq $SEQ · $OMP_NUM_THREADS cores ══"
echo "   (--resume: safe to re-run after ANY disruption — continues from the last 500-iter save)"
# --resume auto-continues from the latest checkpoint if one exists, else starts fresh.
# Saves every 500 iters with optimizer+RNG state, so a disruption never restarts from zero.
python3 pt/train_byte.py --run-id byte_v1_20m --corpus "$CORPUS" \
  --iters "$ITERS" --batch 8 --seq-len "$SEQ" --save-every 500 --device auto --resume

echo "══ export → GGUF (XMIND-consumable, 74 tensors) ══"
python3 pt/export.py --run runs/byte_v1_20m --output gguf/base.gguf

echo ""
echo "✅ Done."
echo "   base run : runs/byte_v1_20m   (safetensors + val_ppl in train_log.jsonl)"
echo "   GGUF     : gguf/base.gguf"
echo "   Next     : download gguf/base.gguf, or push the base to HF Hub, or run"
echo "              spawn_domain_model.sh to mint a NAMED domain model."
echo "   NOTE     : stop/delete the Codespace when done so it stops accruing."
