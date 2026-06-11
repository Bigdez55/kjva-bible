#!/usr/bin/env bash
# train_on_codespace.sh — train the neutral byte base in a GitHub Codespace (CPU).
# Zero burden on your Mac; ~30-60 min full run on a 16-core machine.
#
# Usage (from a Codespace terminal):
#   bash "training/train_on_codespace.sh" smoke   # 300 iters, ~5 min (proof)
#   bash "training/train_on_codespace.sh" full    # 5000 iters → val_ppl ≤ 3.21
#   bash "training/train_on_codespace.sh" 2000    # custom iter count
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"   # training/
cd "$HERE"
export TOKENLESS_HOME="$HERE"
export OMP_NUM_THREADS="$(nproc 2>/dev/null || echo 8)"

MODE="${1:-full}"
case "$MODE" in
  smoke) ITERS=300;  SEQ=512;;
  full)  ITERS=5000; SEQ=1024;;
  *)     ITERS="$MODE"; SEQ=1024;;   # numeric → custom iters
esac

# Corpus lives in training/corpus/ (relative to HERE after cd above).
CORPUS="corpus/eng_kjv_apocrypha_v1/corpus.txt"
[ -f "$CORPUS" ] || { echo "corpus not found at $CORPUS (run from the repo clone)"; exit 1; }

echo "══ Codespace training: $ITERS iters · seq $SEQ · $OMP_NUM_THREADS cores ══"
echo "   (--resume: safe to re-run after ANY disruption — continues from the last 500-iter save)"
# --resume auto-continues from the latest checkpoint if one exists, else starts fresh.
# Saves every 500 iters with optimizer+RNG state, so a disruption never restarts from zero.
python3 scripts/train_byte.py --run-id byte_v1_20m --corpus "$CORPUS" \
  --iters "$ITERS" --batch 8 --seq-len "$SEQ" --save-every 500 --resume

echo "══ export → portable bundle (safetensors + manifest) ══"
python3 scripts/export_byte.py --run-dir "runs/byte_v1_20m" --out-dir "exports/kjv_bringup_v1"

echo ""
echo "Done."
echo "   base run : runs/byte_v1_20m          (safetensors + val_ppl in train_log.jsonl)"
echo "   export   : exports/kjv_bringup_v1/   (portable bundle for inference)"
echo "   Next     : copy exports/ bundle to the inference host, or run"
echo "              scripts/serve_raw_model.py to serve it locally."
echo "   NOTE     : stop/delete the Codespace when done so it stops accruing."
