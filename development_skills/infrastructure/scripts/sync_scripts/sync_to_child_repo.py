#!/usr/bin/env python3
"""Copy a curated subset of ATLAS into a child repo's `development_skills/` directory.

Design notes (issues surfaced 2026-05-04 by LMOS agent):
- `rsync -a` without --delete leaves stale paths after upstream renames (e.g. genesis → starter).
- `19_truth_state/current.truth.yaml` is upstream-identity, not template material; child repos
  must keep their own. We ship only the doctrinal truth-state files (source ranking + stale rules)
  and exclude `current.truth.yaml` so child-authored identity survives re-sync.
- Allowlist now ships only directories that are template/doctrine; identity files are excluded.
"""
import argparse, subprocess, sys
from pathlib import Path

# Script lives at infrastructure/scripts/sync_scripts/ — 3 levels below repo root.
# parents[3] is the ATLAS repo root.
ROOT = Path(__file__).resolve().parents[3]

# Maps source path (relative to ROOT) → destination path inside development_skills/.
# Source paths reflect the post-monorepo-restructure layout (2026-05-04 refactor).
# Destination paths are the canonical names child repos expect.
ALLOWLIST: dict[str, str] = {
    "platform/sdlc/12_agents":              "12_agents",
    "platform/sdlc/13_skills":              "13_skills",
    "platform/sdlc/14_templates":           "14_templates",
    "platform/systems/19_truth_state":      "19_truth_state",
    "platform/systems/24_prompt_library":   "24_prompt_library",
    "infrastructure/scripts":              "infrastructure/scripts",
    "schemas":                              "26_schemas",
    "platform/systems/37_command_protocol": "37_command_protocol",
    "platform/systems/42_context_compiler": "42_context_compiler",
    "docs/APEX_PROTOCOL.md":               "APEX_PROTOCOL.md",
    "README.md":                            "README.md",
}

# Per-path excludes (rsync --exclude) keyed by SOURCE path.
PER_ITEM_EXCLUDES = {
    "platform/systems/19_truth_state": ["current.truth.yaml", "truth_state.registry.yaml"],
}

# Paths inside the child's `development_skills/` that the script should also delete on every
# sync, regardless of allowlist membership, so old top-level dirs from past upstream renames
# do not linger. Add new entries here whenever a top-level dir is renamed/removed upstream;
# remove entries once all known children have synced past the introduction of the entry.
LEGACY_PURGE: list[str] = []

def rsync(src: Path, dst: Path, excludes: list[str] | None = None) -> None:
    cmd = ["rsync", "-a", "--delete"]
    for e in excludes or []:
        cmd += ["--exclude", e]
    if src.is_dir():
        cmd += [str(src) + "/", str(dst) + "/"]
    else:
        cmd += [str(src), str(dst)]
    subprocess.check_call(cmd)

def purge_legacy(dev_skills_dir: Path) -> list[str]:
    removed = []
    for rel in LEGACY_PURGE:
        p = dev_skills_dir / rel
        if p.exists() or p.is_symlink():
            if p.is_dir():
                subprocess.check_call(["rm", "-rf", str(p)])
            else:
                p.unlink()
            removed.append(rel)
    return removed

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", required=True, help="absolute path to child repo")
    ap.add_argument("--no-purge", action="store_true", help="skip LEGACY_PURGE step")
    ap.add_argument(
        "--no-sync-claude-universal",
        action="store_true",
        help="skip syncing ROOT/.claude/universal -> child repo/.claude/universal",
    )
    ap.add_argument(
        "--no-sync-codex-universal",
        action="store_true",
        help="skip syncing ROOT/.codex/universal -> child repo/.codex/universal",
    )
    args = ap.parse_args()

    dst_root = Path(args.target) / "development_skills"
    dst_root.mkdir(parents=True, exist_ok=True)

    if not args.no_purge:
        removed = purge_legacy(dst_root)
        if removed:
            print(f"Purged {len(removed)} legacy paths: {removed}")

    for src_rel, dst_rel in ALLOWLIST.items():
        src = ROOT / src_rel
        if not src.exists():
            print(f"  Skipped (not found): {src_rel}")
            continue
        target = dst_root / dst_rel
        if src.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        rsync(src, target, excludes=PER_ITEM_EXCLUDES.get(src_rel))

    if not args.no_sync_claude_universal:
        claude_src = ROOT / ".claude" / "universal"
        if claude_src.exists():
            claude_dst = Path(args.target) / ".claude" / "universal"
            claude_dst.parent.mkdir(parents=True, exist_ok=True)
            rsync(claude_src, claude_dst)
            print(f"Synced .claude universal bundle into {claude_dst}")
        else:
            print("Skipped .claude universal sync (source missing)")

    if not args.no_sync_codex_universal:
        codex_src = ROOT / ".codex" / "universal"
        if codex_src.exists():
            codex_dst = Path(args.target) / ".codex" / "universal"
            codex_dst.parent.mkdir(parents=True, exist_ok=True)
            rsync(codex_src, codex_dst)
            print(f"Synced .codex universal bundle into {codex_dst}")
        else:
            print("Skipped .codex universal sync (source missing)")

    print(f"Synced {len(ALLOWLIST)} allowlist entries (with --delete) into {dst_root}")
    for src_key, excludes in PER_ITEM_EXCLUDES.items():
        print(f"  Excluded from {Path(src_key).name}/: {excludes}")

if __name__ == "__main__":
    main()
