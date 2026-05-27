#!/usr/bin/env bash
# Install all /apex:* and /atlas:* slash commands from 37_command_protocol/slash_commands/
# into ~/.claude/commands/ so Claude Code resolves them.
# Run this after any playbook update.
set -euo pipefail

# Script lives at infrastructure/scripts/sync_scripts/ — 3 levels below repo root.
REPO_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
SRC="$REPO_ROOT/platform/systems/37_command_protocol/slash_commands"
DST="$HOME/.claude/commands"

mkdir -p "$DST"
count=0
for f in "$SRC"/apex_*.md "$SRC"/atlas_*.md; do
  if [[ ! -f "$f" ]]; then
    continue
  fi
  name="$(basename "$f")"
  dest="${name/apex_/apex:}"
  if [[ "$name" == atlas_* ]]; then
    dest="${name/atlas_/atlas:}"
  fi
  cp "$f" "$DST/$dest"
  count=$((count + 1))
done
echo "Installed $count slash commands to $DST"
