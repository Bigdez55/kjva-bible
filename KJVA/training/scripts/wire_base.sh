#!/usr/bin/env bash
#
# wire_base.sh — Stage a trained base model into training/.
#
# Pulls weights.safetensors + model_config.json + byte_vocab.json from a chosen
# source into this directory so the runtime can find them at canonical paths.
#
# Sources supported:
#
#   --from-run <training/runs/<run-id>>
#       Pulls the latest ckpt_step_*.safetensors (or --ckpt <path>) and the
#       run's model_config.json + byte_vocab.json. Falls back to
#       training/corpus/<corpus-id>/byte_vocab.json if the run dir doesn't
#       carry one.
#
#   --from-promoted <training/bases/<BASE_NAME>>
#       Pulls weights.safetensors + model_config.json + byte_vocab.json that
#       were emitted by `training/scripts/promote_base_model.py`.
#
# Modes (mutually exclusive):
#   --copy        physical copy (default; portable, idempotent)
#   --symlink     symlink instead of copying (faster, but the runtime now
#                 depends on the source path staying live)
#
# Run AFTER training has completed in training/. Run BEFORE the member
# daemons start (they mmap weights.safetensors at startup).
#
# Idempotent: re-running overwrites the staged artefacts.
#
set -euo pipefail

# ─── locate substrate root ──────────────────────────────────────────────────
# scripts/ lives at training/scripts/wire_base.sh.
# SUBSTRATE_ROOT is the dir that holds xmind_federation/, training/, data/, xmind/ — i.e. two
# levels up from this script. In the development repo that's `models/`; in a
# consuming project (after `cp -r models/ my-project/`) that's the project root.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TRAINING_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"        # → training/
SUBSTRATE_ROOT="$(cd "$TRAINING_DIR/.." && pwd)"    # → the dir that holds xmind_federation/, training/, data/

# ─── parse args ──────────────────────────────────────────────────────────────
SOURCE_KIND=""
SOURCE_PATH=""
EXPLICIT_CKPT=""
EXPLICIT_VOCAB=""
MODE="copy"

usage() {
  cat <<EOF
Usage:
  $0 --from-run <run-dir>      [--ckpt <ckpt>] [--vocab <vocab>] [--symlink]
  $0 --from-promoted <base-dir> [--symlink]

Examples:
  $0 --from-run training/runs/byte_v1_20m
  $0 --from-run training/runs/byte_v1_20m --ckpt ckpt_step_005000.safetensors
  $0 --from-promoted models/MY_BASE --symlink
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --from-run)      SOURCE_KIND="run";       SOURCE_PATH="$2"; shift 2 ;;
    --from-promoted) SOURCE_KIND="promoted";  SOURCE_PATH="$2"; shift 2 ;;
    --ckpt)          EXPLICIT_CKPT="$2";      shift 2 ;;
    --vocab)         EXPLICIT_VOCAB="$2";     shift 2 ;;
    --copy)          MODE="copy";             shift ;;
    --symlink)       MODE="symlink";          shift ;;
    -h|--help)       usage; exit 0 ;;
    *) echo "unknown arg: $1" >&2; usage; exit 2 ;;
  esac
done

if [ -z "$SOURCE_KIND" ]; then
  usage; exit 2
fi

# ─── resolve source paths ────────────────────────────────────────────────────
# Allow SOURCE_PATH to be relative to SUBSTRATE_ROOT or absolute.
if [ -d "$SOURCE_PATH" ]; then
  SRC_DIR="$(cd "$SOURCE_PATH" && pwd)"
elif [ -d "$SUBSTRATE_ROOT/$SOURCE_PATH" ]; then
  SRC_DIR="$(cd "$SUBSTRATE_ROOT/$SOURCE_PATH" && pwd)"
else
  echo "✗ source dir not found: $SOURCE_PATH" >&2
  exit 1
fi

WEIGHTS_SRC=""
CONFIG_SRC=""
VOCAB_SRC=""

if [ "$SOURCE_KIND" = "run" ]; then
  # weights: explicit ckpt, or latest ckpt_step_*.safetensors
  if [ -n "$EXPLICIT_CKPT" ]; then
    if [ -f "$SRC_DIR/$EXPLICIT_CKPT" ]; then
      WEIGHTS_SRC="$SRC_DIR/$EXPLICIT_CKPT"
    elif [ -f "$EXPLICIT_CKPT" ]; then
      WEIGHTS_SRC="$(cd "$(dirname "$EXPLICIT_CKPT")" && pwd)/$(basename "$EXPLICIT_CKPT")"
    else
      echo "✗ --ckpt not found: $EXPLICIT_CKPT" >&2
      exit 1
    fi
  else
    # find latest ckpt_step_*.safetensors
    LATEST=""
    for f in "$SRC_DIR"/ckpt_step_*.safetensors; do
      [ -e "$f" ] || continue
      LATEST="$f"
    done
    if [ -z "$LATEST" ]; then
      # also accept a single weights.safetensors directly
      if [ -f "$SRC_DIR/weights.safetensors" ]; then
        WEIGHTS_SRC="$SRC_DIR/weights.safetensors"
      else
        echo "✗ no ckpt_step_*.safetensors (or weights.safetensors) under $SRC_DIR" >&2
        exit 1
      fi
    else
      WEIGHTS_SRC="$LATEST"
    fi
  fi

  CONFIG_SRC="$SRC_DIR/model_config.json"
  if [ ! -f "$CONFIG_SRC" ]; then
    echo "✗ model_config.json not found in run dir: $CONFIG_SRC" >&2
    exit 1
  fi

  # vocab: prefer run dir's, fall back to corpus, fall back to --vocab override
  if [ -n "$EXPLICIT_VOCAB" ]; then
    VOCAB_SRC="$EXPLICIT_VOCAB"
  elif [ -f "$SRC_DIR/byte_vocab.json" ]; then
    VOCAB_SRC="$SRC_DIR/byte_vocab.json"
  else
    # autodetect under training/corpus/*/byte_vocab.json
    for c in "$SUBSTRATE_ROOT/training/corpus"/*/byte_vocab.json; do
      [ -e "$c" ] || continue
      VOCAB_SRC="$c"
      break
    done
  fi

elif [ "$SOURCE_KIND" = "promoted" ]; then
  WEIGHTS_SRC="$SRC_DIR/weights.safetensors"
  CONFIG_SRC="$SRC_DIR/model_config.json"
  VOCAB_SRC="$SRC_DIR/byte_vocab.json"
  for f in "$WEIGHTS_SRC" "$CONFIG_SRC" "$VOCAB_SRC"; do
    if [ ! -f "$f" ]; then
      echo "✗ promoted base missing: $f" >&2
      exit 1
    fi
  done
fi

# ─── stage ───────────────────────────────────────────────────────────────────
stage_one() {
  local src="$1"
  local dst="$2"
  local label="$3"
  if [ -z "$src" ]; then
    echo "  ⚠ no source for $label — skipping"
    return 0
  fi
  if [ ! -f "$src" ]; then
    echo "  ⚠ $label source missing: $src — skipping"
    return 0
  fi
  mkdir -p "$(dirname "$dst")"
  if [ -e "$dst" ] || [ -L "$dst" ]; then
    rm -f "$dst"
  fi
  if [ "$MODE" = "symlink" ]; then
    ln -s "$src" "$dst"
    echo "  ✓ $label  →  $dst  (symlink)"
  else
    cp "$src" "$dst"
    echo "  ✓ $label  →  $dst"
  fi
}

echo "── staging into $TRAINING_DIR ──"
echo "  mode:   $MODE"
echo "  source: $SRC_DIR  ($SOURCE_KIND)"
echo ""

stage_one "$WEIGHTS_SRC" "$TRAINING_DIR/weights.safetensors"    "weights"
stage_one "$CONFIG_SRC"  "$TRAINING_DIR/model_config.json"      "config"
stage_one "$VOCAB_SRC"   "$TRAINING_DIR/byte_vocab.json"        "vocab"

# Optional: drop a provenance breadcrumb so the next operator can see what was staged
cat > "$TRAINING_DIR/.staged_from" <<EOF
source_kind=$SOURCE_KIND
source_dir=$SRC_DIR
weights=${WEIGHTS_SRC:-}
config=${CONFIG_SRC:-}
vocab=${VOCAB_SRC:-}
mode=$MODE
staged_at=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
EOF
chmod 600 "$TRAINING_DIR/.staged_from"

echo ""
echo "✓ base staged. Next:"
echo "    ./training/scripts/wire_all.sh"
echo "    python3 training/scripts/serve_raw_model.py --export training"
