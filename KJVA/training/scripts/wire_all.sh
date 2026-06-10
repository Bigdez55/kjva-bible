#!/usr/bin/env bash
#
# wire_all.sh — Publish trained adapters into the runtime.
#
# Discovers members from xmind_federation/personas/*.txt (one persona file per member).
# For each discovered member, looks for an adapter at one of:
#   training/adapters/<member>/adapter.safetensors           (member-named dir)
#   training/adapters/gated/<member>/adapter.safetensors     (promoted via
#                                                             validate_adapter.py)
#   training/adapters/gated/lora_<member>/adapter.safetensors (PEFT-method prefix)
# and writes that absolute path into:
#   data/soul/<member>/.adapter
#
# The member daemons read .adapter at startup and call xmind_easy_load_adapter().
#
# Run AFTER:
#   1. base is staged (training/weights.safetensors via wire_base.sh)
#   2. per-member adapters are trained + (optionally) promoted via
#      training/scripts/validate_adapter.py promote
#
# Member-agnostic by design — no member names hard-coded.
#
set -euo pipefail
cd "$(dirname "$0")/../.."   # → substrate root (the dir that contains xmind_federation/, training/, data/)

PERSONA_DIR="xmind_federation/personas"
ADAPTER_DIR="training/adapters"
SOUL_DIR="data/soul"

usage() {
  sed -n '2,22p' "$0"
}

case "${1:-}" in
  -h|--help) usage; exit 0 ;;
  "") : ;;
  *) echo "unknown arg: $1" >&2; usage; exit 2 ;;
esac

if [ ! -d "$PERSONA_DIR" ]; then
  echo "✗ $PERSONA_DIR not found — no members declared yet."
  echo "  Create $PERSONA_DIR/<member>.txt for each member first."
  exit 1
fi

# Discover members from persona files (filename minus .txt; skip _template.txt + README)
MEMBERS=()
for f in "$PERSONA_DIR"/*.txt; do
  [ -f "$f" ] || continue
  base="$(basename "$f" .txt)"
  case "$base" in
    _*|README) continue ;;
  esac
  MEMBERS+=("$base")
done

if [ ${#MEMBERS[@]} -eq 0 ]; then
  echo "✗ no member personas found in $PERSONA_DIR/"
  echo "  Create <member-name>.txt for each member, then re-run."
  exit 1
fi

echo "── discovered ${#MEMBERS[@]} member(s) ──"
printf '  %s\n' "${MEMBERS[@]}"
echo ""

MISSING=()
WIRED=0

for m in "${MEMBERS[@]}"; do
  adapter_path=""
  # Search order: member-named dir, then gated/<m>, then gated/lora_<m>
  for cand_dir in \
      "$ADAPTER_DIR/$m" \
      "$ADAPTER_DIR/gated/$m" \
      "$ADAPTER_DIR/gated/lora_$m" \
      "$ADAPTER_DIR/staging/$m" \
      "$ADAPTER_DIR/staging/lora_$m"; do
    for fname in adapter.safetensors adapter.npz weights.safetensors model.safetensors; do
      if [ -f "$cand_dir/$fname" ]; then
        adapter_path="$(cd "$cand_dir" && pwd)/$fname"
        break 2
      fi
    done
  done

  if [ -z "$adapter_path" ]; then
    MISSING+=("$m")
    continue
  fi

  mkdir -p "$SOUL_DIR/$m"
  echo "$adapter_path" > "$SOUL_DIR/$m/.adapter"
  chmod 600 "$SOUL_DIR/$m/.adapter"
  echo "  ✓ $m → $adapter_path"
  WIRED=$((WIRED+1))
done

echo ""
echo "  wired:   $WIRED / ${#MEMBERS[@]}"
echo "  missing: ${#MISSING[@]}"

if [ ${#MISSING[@]} -gt 0 ]; then
  echo "  not yet trained: ${MISSING[*]}"
  echo "  Train an adapter for each missing member, then re-run:"
  echo "    python3 training/scripts/train_peft.py \\"
  echo "      --method lora --domains <member> \\"
  echo "      --base-checkpoint training/weights.safetensors \\"
  echo "      --output training/adapters/staging/lora_<member>"
  echo "    python3 training/scripts/validate_adapter.py promote \\"
  echo "      --adapter training/adapters/staging/lora_<member>"
  echo "    $0"
fi

echo ""
echo "Member daemons will pick up the adapter on next start (read $SOUL_DIR/<m>/.adapter)."
