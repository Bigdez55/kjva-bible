#!/usr/bin/env python3
"""
audit_production_runtime_authority.py — Phase-2 production gate.

Enforces SINGLE RUNTIME AUTHORITY for the KJVA-1 / XMIND-1 production candidate.
The production stack ships canonical.gguf + retrieval + governance ONLY. No
archived candidate (SFT / Omni-PEFT v1/v2/v2.1 / tournament) may be runtime-
authoritative, and none may auto-load.

FAILS (exit 1) if any of:
  - more than one .gguf exists at training/gguf root
  - the sole root .gguf is not canonical.gguf
  - the runtime weight-resolution probe list (_find_weights) references archive/
  - the runtime adapter resolver (_find_adapter) has a non-env default (auto-load)
  - canonical.gguf SHA-256 mismatches PRODUCTION_MANIFEST.json (when present)

Usage: python3 audit_production_runtime_authority.py [--manifest PATH]
Exit 0 = PASS.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

_V7 = Path(__file__).resolve().parent.parent          # models v7/
_GGUF_ROOT = _V7 / "training" / "gguf"
_CLIENT = _V7 / "ai" / "tokenless-agent" / "src" / "_xmind" / "client.py"


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    h.update(p.read_bytes())
    return h.hexdigest()


def _check(name: str, ok: bool, detail: str, failures: list) -> None:
    mark = "PASS" if ok else "FAIL"
    print(f"  [{mark}] {name}: {detail}")
    if not ok:
        failures.append(name)


def _default_manifest() -> Path:
    """Locate PRODUCTION_MANIFEST.json across layouts:
      - substrate-in-repo (models v7 nested): manifest at repo root = _V7.parent
      - deployed project (models v7 contents ARE the repo root): manifest at _V7
    """
    for cand in (_V7 / "PRODUCTION_MANIFEST.json", _V7.parent / "PRODUCTION_MANIFEST.json"):
        if cand.exists():
            return cand
    return _V7 / "PRODUCTION_MANIFEST.json"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", default=str(_default_manifest()))
    args = ap.parse_args()
    failures: list = []
    print("=== PRODUCTION RUNTIME AUTHORITY AUDIT ===")

    # 1. exactly one .gguf at the gguf root, and it is canonical.gguf
    root_ggufs = sorted(p.name for p in _GGUF_ROOT.glob("*.gguf"))
    _check("single_root_gguf", root_ggufs == ["canonical.gguf"],
           f"root .gguf = {root_ggufs}", failures)

    # 2. canonical.gguf exists
    canonical = _GGUF_ROOT / "canonical.gguf"
    _check("canonical_exists", canonical.exists(),
           str(canonical.relative_to(_V7)), failures)

    # 3. runtime weight resolution must NOT reference archive/
    client_src = _CLIENT.read_text() if _CLIENT.exists() else ""
    fw = re.search(r"def _find_weights.*?return None", client_src, re.S)
    fw_body = fw.group(0) if fw else ""
    _check("weights_resolution_no_archive", bool(fw_body) and "archive" not in fw_body,
           "no 'archive' path in _find_weights probe list", failures)
    _check("weights_resolution_has_canonical", "canonical.gguf" in fw_body,
           "_find_weights probes canonical.gguf", failures)

    # 4. adapter resolver must be env-only (no default auto-load)
    fa = re.search(r"def _find_adapter.*?return None", client_src, re.S)
    fa_body = fa.group(0) if fa else ""
    # all sources must come from os.environ.get(...); flag any string path default
    env_only = bool(fa_body) and "os.environ.get" in fa_body and \
        not re.search(r"_V7\s*/|training\s*/|archive|\.gguf|\.safetensors", fa_body)
    _check("adapter_no_autoload", env_only,
           "adapters are opt-in via env var only (no auto-load default)", failures)

    # 5. no archived candidate sits at the runtime root (only under archive/)
    archive_dir = _GGUF_ROOT / "archive"
    stray = [p.name for p in _GGUF_ROOT.glob("*.gguf") if p.name != "canonical.gguf"]
    _check("no_candidate_at_root", not stray,
           f"stray root candidates = {stray or 'none'}", failures)

    # 6. canonical SHA matches the production manifest (when present)
    manifest_path = Path(args.manifest)
    if manifest_path.exists() and canonical.exists():
        man = json.loads(manifest_path.read_text())
        recorded = (man.get("sha256") or "").lower()
        actual = _sha256(canonical)
        match = bool(recorded) and actual.startswith(recorded.replace("…", "").rstrip("."))
        _check("canonical_sha_matches_manifest", match,
               f"manifest={recorded[:16]}… actual={actual[:16]}…", failures)
    else:
        print(f"  [INFO] manifest not found ({manifest_path.name}); SHA cross-check skipped")

    print(f"\nSummary: {'PASS' if not failures else 'FAIL'} "
          f"({len(failures)} failure(s){': ' + ', '.join(failures) if failures else ''})")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
