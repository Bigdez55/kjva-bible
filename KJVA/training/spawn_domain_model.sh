#!/usr/bin/env bash
# spawn_domain_model.sh — mass-produce a NAMED domain model from the neutral base.
#
# The base model (training/pt/, this build) is identity-neutral by design. A domain
# model = neutral base + domain corpus + a NAME applied at derive time. This script is
# the repeatable recipe so you never redo the substrate build per domain.
#
# Usage:
#   training/spawn_domain_model.sh \
#       --name TransitGPT --domain transportation \
#       --corpus path/to/transit_corpus.txt \
#       --base-run runs/tokenless_base_v1 \
#       [--steps 200] [--device auto] [--method lora]
#
# Produces (under training/):
#   gguf/<name>.gguf            — the base, exported + NAMED (general.name=<name>)
#   adapters/domains/<name>/    — the validated domain PEFT adapter
#   docs/domains/<name>_MODEL_CARD.md
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"   # training/
V7="$(cd "$HERE/.." && pwd)"

NAME="" DOMAIN="" CORPUS="" BASE_RUN="" STEPS=200 DEVICE="auto" METHOD="lora" PUSH_HF=0
while [ $# -gt 0 ]; do
  case "$1" in
    --name) NAME="$2"; shift 2;;
    --domain) DOMAIN="$2"; shift 2;;
    --corpus) CORPUS="$2"; shift 2;;
    --base-run) BASE_RUN="$2"; shift 2;;
    --steps) STEPS="$2"; shift 2;;
    --device) DEVICE="$2"; shift 2;;
    --method) METHOD="$2"; shift 2;;
    --push-hf) PUSH_HF=1; shift;;     # publish the named model to a PRIVATE HF repo
    *) echo "unknown arg: $1" >&2; exit 2;;
  esac
done
[ -n "$NAME" ] && [ -n "$CORPUS" ] && [ -n "$BASE_RUN" ] || {
  echo "required: --name <Name> --corpus <corpus.txt> --base-run <run dir>" >&2; exit 2; }
[ -z "$DOMAIN" ] && DOMAIN="$NAME"
SLUG="$(echo "$NAME" | tr '[:upper:] ' '[:lower:]_' )"

cd "$HERE"
echo "═══ Spawning domain model '$NAME' (domain=$DOMAIN) from base $BASE_RUN ═══"

# 1. Domain PEFT fine-tune from the shared neutral base.
ADAPTER_DIR="adapters/domains/$SLUG"
echo "── 1/4  fine-tune ($METHOD) on $CORPUS"
python3 pt/train_peft.py --method "$METHOD" --base-checkpoint "$BASE_RUN" \
  --corpus "$CORPUS" --steps "$STEPS" --device "$DEVICE" --output "$ADAPTER_DIR"

# 2. Validate the domain adapter (promotion gate).
echo "── 2/4  validate adapter"
python3 scripts/validate_adapter.py check --adapter "$ADAPTER_DIR"

# 3. Export the base as a NAMED domain GGUF (this is the 'naming' step).
mkdir -p gguf
GGUF="gguf/${SLUG}.gguf"
echo "── 3/4  export NAMED GGUF → $GGUF  (general.name=$NAME)"
python3 pt/export.py --run "$BASE_RUN" --name "$NAME" --domain "$DOMAIN" --output "$GGUF"

# 4. Write the domain model card.
echo "── 4/4  model card"
mkdir -p "$V7/docs/domains"
CARD="$V7/docs/domains/${SLUG}_MODEL_CARD.md"
cat > "$CARD" <<EOF
# Domain Model: $NAME

- **Domain:** $DOMAIN
- **Base:** Tokenless neutral byte base (18,980,352 params; see BASE_MODEL_CARD.md)
- **Derived from base run:** $BASE_RUN
- **Adapter:** $ADAPTER_DIR ($METHOD, validated)
- **Named GGUF:** training/$GGUF (general.name=$NAME, general.domain=$DOMAIN)
- **Corpus:** $CORPUS

## Deploy
Load training/$GGUF in the XMIND runtime; apply the adapter via the XMIND adapter
runtime (or merge). The model self-identifies as "$NAME" via GGUF general.name.
EOF
echo "✓ Spawned '$NAME' → $GGUF  +  $ADAPTER_DIR  +  $CARD"

# 5. (optional) publish to a PRIVATE Hugging Face repo.
if [ "$PUSH_HF" = "1" ]; then
  echo "── 5/5  publish to PRIVATE HF repo (tokenless-domain-$SLUG)"
  python3 push_to_hf.py --repo "tokenless-domain-$SLUG" --card "$CARD" \
    --files "$GGUF" "$ADAPTER_DIR/adapter.safetensors" "$ADAPTER_DIR/adapter_genome.json"
fi
