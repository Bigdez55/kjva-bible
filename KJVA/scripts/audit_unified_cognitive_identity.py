#!/usr/bin/env python3
"""
audit_unified_cognitive_identity.py — Hard-fail audit of the Unified Cognitive
Identity Contract in models v7/.

Doctrine (canonical phrase):

    Identity is singular. Engineering surfaces remain auditable. Cognitive
    flow remains fused.

Short form:

    One cognitive identity. Auditable engineering surfaces. Fluid
    depth-scaled cognition.

This script enforces the doctrine MECHANICALLY. It fails hard (non-zero exit)
on ANY drift finding. It is intended to be run:

  - Before any GGUF promotion ceremony.
  - As a CI gate.
  - From the project_canonical_base_doctrine memory + the
    CANONICAL_BASE_DOCTRINE.md / Unified Cognitive Identity Contract.

Usage:
    python3 scripts/audit_unified_cognitive_identity.py
    python3 scripts/audit_unified_cognitive_identity.py --json
    python3 scripts/audit_unified_cognitive_identity.py --root "models v7"   # if run from repo root

Exit codes:
    0  all checks PASS
    1  one or more checks FAIL (drift detected)
    2  invocation error
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

# ────────────────────────────────────────────────────────────────────────
# Doctrine constants
# ────────────────────────────────────────────────────────────────────────

CANONICAL_PHRASE = (
    "Identity is singular. Engineering surfaces remain auditable. "
    "Cognitive flow remains fused."
)
SHORT_FORM = (
    "One cognitive identity. Auditable engineering surfaces. "
    "Fluid depth-scaled cognition."
)

# Forbidden drift — every phrase below MUST be absent from active doctrine,
# code, and json under models v7/. Each phrase appears in `is_not` lists or
# in historical narration is exempted via the contextualization tokens below.
FORBIDDEN_DRIFT_PHRASES = [
    "three layers of identity control stay separate",
    "separate cognitive identities",
    "separate minds",
    "separate cognition layers",
    "manual cognition layer switching",
    "training-stage choice",
    "training state choice",
    "training-state choice",
    # These two are forbidden as STANDALONE assertions — but the new
    # doctrine doc legitimately quotes them as forbidden patterns. We check
    # them with a contextualization escape (see FORBIDDEN_CTX).
    "substrate is not cognition",
    "substrate ≠ cognition",
]

# Phrases that, when present in the SAME paragraph/line as a forbidden drift
# phrase, mark the forbidden phrase as "rejected language" rather than active
# doctrine. This lets the audit see "forbidden: training-stage choice" as
# meta-mention rather than active assertion.
FORBIDDEN_CTX_TOKENS = [
    "forbidden",
    "do not",
    "does not",
    "do not say",
    "do not use",
    "drift",
    "rejected",
    "replace",
    "is_not",
    "previously",
    "historical",
    "rather than",
    "instead",
    "not merely",
    "not only",
    "are not",
    "is not",
    "must never",
    "must not",
    "never be",
    "never become",
    "never",
    "as if they were",
    "treated as",
    "may not",
    "is_NOT",
    "false separation",
    "creates false",
    "definitional",
    "FORBIDDEN_DRIFT_PHRASES",
    "FORBIDDEN_CTX_TOKENS",
    "previous practice",
    "prior practice",
    "retrospective only",
    "fused cognitive flow",
]

# Files where forbidden phrases are KNOWN to appear definitionally —
# the audit script's own list, JSON `is_not` arrays, the doctrine test
# gate, and the behavioral-test gate. Allowlist is intentionally tiny
# and each entry must satisfy ONE of:
#   (a) Contains a literal data structure of forbidden phrases used by
#       the audit itself (FORBIDDEN_DRIFT_PHRASES list).
#   (b) Is a spec JSON whose `is_not` arrays definitionally enumerate
#       what the canonical identity is NOT.
#   (c) Is a test file whose body enumerates forbidden phrases to assert
#       their behavior (rejection or detection).
# Allowlist is enforced by `assert_allowlist_is_justified()` at runtime so
# new entries cannot be added without an explicit data-structure marker.
ALLOWLIST_DEFINITIONAL_FILES = {
    # (a) — audit script holds the canonical list
    "scripts/audit_unified_cognitive_identity.py": "FORBIDDEN_DRIFT_PHRASES",
    # (c) — doctrine pytest gate
    "tests/test_unified_cognitive_identity.py": "CANONICAL_PHRASE",
    # (c) — behavioral pytest gate (forbidden phrases appear in test prompts)
    "tests/test_fluid_depth_scaled_cognition.py": "test_10_no_identity_fork_under_any_signal",
    # (b) — spec JSON's `is_not` arrays
    "heptagon/unified_model_spec.json": '"is_not"',
}


def assert_allowlist_is_justified(root: Path) -> list[str]:
    """Every allowlisted file MUST contain its declared justification marker
    in its raw text. If a marker is missing, the allowlist is being abused
    and the audit returns a finding (does not silently skip)."""
    findings: list[str] = []
    for rel, marker in ALLOWLIST_DEFINITIONAL_FILES.items():
        p = root / rel
        if not p.exists():
            findings.append(f"allowlist file missing on disk: {rel}")
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            findings.append(f"allowlist file unreadable: {rel} ({e})")
            continue
        if marker not in text:
            findings.append(
                f"allowlist abuse: {rel} no longer contains its declared "
                f"justification marker {marker!r}"
            )
    return findings

# Files where the canonical phrase MUST appear at least once (as active doctrine).
REQUIRED_PHRASE_FILES = [
    "training/gguf/CANONICAL_BASE_DOCTRINE.md",
    "training/gguf/promotion/PROMOTION_RECORD.md",
    "training/gguf/promotion/lineage_manifest.json",
    "training/gguf/promotion/benchmark_table.json",
    "training/gguf/canonical.gguf.json",
]

# Files/paths the doctrine requires to exist.
REQUIRED_PATHS = [
    "training/gguf/canonical.gguf",
    "training/gguf/canonical.gguf.json",
    "training/gguf/CANONICAL_BASE_DOCTRINE.md",
    "training/gguf/promotion/PROMOTION_RECORD.md",
    "training/gguf/promotion/lineage_manifest.json",
    "training/gguf/promotion/benchmark_table.json",
    "training/gguf/promotion/evidence",
    "training/gguf/archive",
    "scripts/audit_unified_cognitive_identity.py",
    "tests/test_unified_cognitive_identity.py",
    "tests/test_fluid_depth_scaled_cognition.py",
    "ai/tokenless-agent/src/cognitive_depth_trace.py",
]


# ────────────────────────────────────────────────────────────────────────
# Result dataclasses
# ────────────────────────────────────────────────────────────────────────

@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str
    findings: list[str] = field(default_factory=list)


# ────────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────────

def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _has_ctx(text: str) -> bool:
    low = text.lower()
    return any(tok.lower() in low for tok in FORBIDDEN_CTX_TOKENS)


def _is_forbidden_active_in_paragraph(
    lines: list[str], idx: int, window: int = 3,
) -> bool:
    """Return True if the line at `idx` contains a forbidden phrase AND
    NO context token appears within ±window lines (paragraph window)."""
    line = lines[idx]
    low = line.lower()
    has_forbidden = any(p in low for p in FORBIDDEN_DRIFT_PHRASES)
    if not has_forbidden:
        return False
    lo = max(0, idx - window)
    hi = min(len(lines), idx + window + 1)
    paragraph = "\n".join(lines[lo:hi])
    return not _has_ctx(paragraph)


def scan_for_forbidden(root: Path, exclude_dirs: set[str]) -> list[str]:
    """Walk all text-ish files under root, flag lines with active-doctrine
    forbidden phrases (not contextualized within a ±3 line window)."""
    findings: list[str] = []
    suffixes = {".md", ".py", ".json", ".yaml", ".yml", ".txt"}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in exclude_dirs and not d.startswith(".")]
        for fn in filenames:
            if not any(fn.endswith(s) for s in suffixes):
                continue
            p = Path(dirpath) / fn
            try:
                rel = p.relative_to(root).as_posix()
            except ValueError:
                continue
            # Allowlist files that contain forbidden phrases by design
            # (audit lists, JSON is_not arrays, doctrine test gates).
            if rel in ALLOWLIST_DEFINITIONAL_FILES:
                continue
            try:
                text = p.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            lines = text.splitlines()
            for i, line in enumerate(lines):
                if _is_forbidden_active_in_paragraph(lines, i, window=3):
                    findings.append(f"{rel}:{i+1}: {line.strip()[:160]}")
    return findings


# ────────────────────────────────────────────────────────────────────────
# Individual checks
# ────────────────────────────────────────────────────────────────────────

def check_canonical_phrase_present(root: Path) -> CheckResult:
    missing = []
    for rel in REQUIRED_PHRASE_FILES:
        p = root / rel
        if not p.exists():
            missing.append(f"MISSING FILE: {rel}")
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            missing.append(f"UNREADABLE: {rel} ({e})")
            continue
        if CANONICAL_PHRASE not in text:
            missing.append(f"PHRASE NOT FOUND: {rel}")
    return CheckResult(
        name="canonical_phrase_present_in_required_files",
        passed=not missing,
        detail=(
            f"The canonical doctrine phrase must appear verbatim in each of the "
            f"{len(REQUIRED_PHRASE_FILES)} required files."
        ),
        findings=missing,
    )


def check_no_active_drift(root: Path) -> CheckResult:
    findings = scan_for_forbidden(
        root,
        exclude_dirs={
            "build", "dist", ".venv", "venv", "__pycache__",
            "archive",            # historical embodiments — narration allowed
            "_archive",
            "benchmark_results",  # benchmark output reports — narration allowed
            "node_modules",
        },
    )
    return CheckResult(
        name="no_active_drift_phrases",
        passed=not findings,
        detail=(
            "No forbidden drift phrase may appear as an active assertion in "
            "doctrine / code / metadata. Mentions are allowed only with "
            "contextualization tokens (forbidden / do not / drift / replace / "
            "is_not / historical / rather than / instead)."
        ),
        findings=findings,
    )


def check_allowlist_not_abused(root: Path) -> CheckResult:
    """Ensure every allowlisted file still contains its declared
    justification marker. Prevents the allowlist from silently becoming
    a doctrine loophole."""
    findings = assert_allowlist_is_justified(root)
    return CheckResult(
        name="allowlist_not_abused",
        passed=not findings,
        detail=(
            "Each allowlisted file must still contain the data-structure "
            "marker that justifies its exemption (audit script's "
            "FORBIDDEN_DRIFT_PHRASES, JSON `is_not` arrays, or a tagged "
            "test body). An allowlisted file without its marker is a loophole."
        ),
        findings=findings,
    )


def check_depth_trace_module_present(root: Path) -> CheckResult:
    """The fluid-depth trace module must exist and expose the singular
    IDENTITY_ID, the surface constants, and the build_trace function."""
    p = root / "ai" / "tokenless-agent" / "src" / "cognitive_depth_trace.py"
    if not p.exists():
        return CheckResult(
            name="depth_trace_module_present",
            passed=False,
            detail="ai/tokenless-agent/src/cognitive_depth_trace.py must exist.",
            findings=[f"missing: {p.relative_to(root)}"],
        )
    text = p.read_text(encoding="utf-8", errors="replace")
    required_symbols = [
        "IDENTITY_ID",
        "ALL_SURFACES",
        "class DepthSignals",
        "class CognitiveDepthTrace",
        "def estimate_depth_signals",
        "def activate_surfaces",
        "def build_trace",
        "DOCTRINE_PHRASE",
    ]
    missing = [s for s in required_symbols if s not in text]
    return CheckResult(
        name="depth_trace_module_present",
        passed=not missing,
        detail=(
            "cognitive_depth_trace.py must expose: IDENTITY_ID, ALL_SURFACES, "
            "DepthSignals, CognitiveDepthTrace, estimate_depth_signals(), "
            "activate_surfaces(), build_trace(), and the canonical "
            "DOCTRINE_PHRASE."
        ),
        findings=[f"missing symbol: {m}" for m in missing],
    )


def check_behavioral_test_present(root: Path) -> CheckResult:
    """The behavioral test gate must exist with ≥8 test methods."""
    p = root / "tests" / "test_fluid_depth_scaled_cognition.py"
    if not p.exists():
        return CheckResult(
            name="behavioral_test_present",
            passed=False,
            detail="tests/test_fluid_depth_scaled_cognition.py must exist.",
            findings=[f"missing: {p.relative_to(root)}"],
        )
    text = p.read_text(encoding="utf-8", errors="replace")
    test_methods = re.findall(r"def test_\d+_\w+", text)
    if len(test_methods) < 8:
        return CheckResult(
            name="behavioral_test_present",
            passed=False,
            detail="Behavioral test must define ≥8 test methods.",
            findings=[f"found {len(test_methods)} test methods; need ≥8"],
        )
    return CheckResult(
        name="behavioral_test_present",
        passed=True,
        detail=f"Behavioral test defines {len(test_methods)} test methods.",
    )


def check_required_paths_exist(root: Path) -> CheckResult:
    missing = []
    for rel in REQUIRED_PATHS:
        p = root / rel
        if not p.exists():
            missing.append(f"MISSING: {rel}")
    return CheckResult(
        name="required_doctrine_paths_exist",
        passed=not missing,
        detail="All doctrine-required artifacts must exist on disk.",
        findings=missing,
    )


def check_canonical_sha_matches_manifest(root: Path) -> CheckResult:
    can_path = root / "training/gguf/canonical.gguf"
    man_path = root / "training/gguf/promotion/lineage_manifest.json"
    if not can_path.exists() or not man_path.exists():
        return CheckResult(
            name="canonical_sha_matches_manifest",
            passed=False,
            detail="canonical.gguf and lineage_manifest.json must both exist.",
            findings=[f"Missing: {can_path if not can_path.exists() else man_path}"],
        )
    try:
        manifest = json.loads(man_path.read_text())
    except Exception as e:
        return CheckResult(
            name="canonical_sha_matches_manifest",
            passed=False,
            detail="lineage_manifest.json must be valid JSON.",
            findings=[f"JSON parse error: {e}"],
        )
    expected = manifest.get("canonical", {}).get("sha256", "")
    actual = sha256_file(can_path)
    if expected != actual:
        return CheckResult(
            name="canonical_sha_matches_manifest",
            passed=False,
            detail="canonical.gguf SHA-256 must equal lineage_manifest.json canonical.sha256.",
            findings=[
                f"manifest:  {expected}",
                f"on-disk:   {actual}",
            ],
        )
    return CheckResult(
        name="canonical_sha_matches_manifest",
        passed=True,
        detail=f"canonical.gguf SHA-256 matches manifest (sha256={actual[:32]}…).",
    )


def check_runtime_default_points_at_canonical(root: Path) -> CheckResult:
    client_paths = [
        root / "xmind_federation/client.py",
        root / "_xmind/client.py",
    ]
    findings = []
    found_at_least_one = False
    for cp in client_paths:
        if not cp.exists():
            continue
        found_at_least_one = True
        text = cp.read_text(encoding="utf-8", errors="replace")
        if 'training" / "gguf" / "canonical.gguf"' not in text and 'training/gguf/canonical.gguf' not in text:
            findings.append(
                f"{cp.relative_to(root)}: default model_path does not resolve to "
                f"training/gguf/canonical.gguf"
            )
    if not found_at_least_one:
        findings.append("No XMindClient file found at xmind_federation/client.py or _xmind/client.py")
    return CheckResult(
        name="runtime_default_points_at_canonical",
        passed=not findings,
        detail="XMindClient default model_path must resolve to training/gguf/canonical.gguf.",
        findings=findings,
    )


def check_no_folder_scan_for_runtime_base(root: Path) -> CheckResult:
    """The runtime base must NOT be chosen by globbing the gguf folder."""
    findings = []
    for rel in [
        "xmind_federation/client.py",
        "_xmind/client.py",
        "ai/tokenless-agent/src/cognitive_pipeline.py",
        "ai/tokenless-agent/src/agent.py",
    ]:
        p = root / rel
        if not p.exists():
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        for pattern_re, label in [
            (r'glob\s*\(\s*["\'][^"\']*\.gguf', "glob(*.gguf) found"),
            (r'glob\s*\(\s*["\'][^"\']*\.safetensors', "glob(*.safetensors) found"),
            (r'sorted\s*\([^)]*\.gguf', "sorted(...gguf) found"),
            (r'os\.listdir\s*\([^)]*gguf', "listdir(gguf...) found"),
        ]:
            for lineno, line in enumerate(text.splitlines(), start=1):
                if re.search(pattern_re, line):
                    findings.append(f"{rel}:{lineno}: {label} — {line.strip()[:120]}")
    return CheckResult(
        name="no_folder_scan_for_runtime_base",
        passed=not findings,
        detail="No runtime code path may choose the canonical base by scanning a gguf folder.",
        findings=findings,
    )


def check_cognitive_pipeline_single_entry(root: Path) -> CheckResult:
    p = root / "ai/tokenless-agent/src/cognitive_pipeline.py"
    if not p.exists():
        return CheckResult(
            name="cognitive_pipeline_single_entry",
            passed=False,
            detail="cognitive_pipeline.py must exist.",
            findings=[f"Missing: {p.relative_to(root)}"],
        )
    text = p.read_text(encoding="utf-8", errors="replace")
    findings = []
    if "class CognitivePipeline" not in text:
        findings.append("class CognitivePipeline not found")
    if "def get_pipeline" not in text:
        findings.append("singleton accessor get_pipeline() not found")
    # The execute() method is the single fused entry.
    if "async def execute" not in text:
        findings.append("async def execute(...) entry method not found")
    return CheckResult(
        name="cognitive_pipeline_single_entry",
        passed=not findings,
        detail=(
            "CognitivePipeline must be the single fused entry to the cognitive "
            "flow (class + singleton + async execute)."
        ),
        findings=findings,
    )


def check_engineering_surfaces_present(root: Path) -> CheckResult:
    """Each named engineering surface must have at least one source file."""
    surfaces = {
        "architecture (xmind)":   ["ai/xmind/include/xmind.h", "ai/xmind/src/interp_tokenless.c"],
        "promotion":              ["training/gguf/canonical.gguf", "training/gguf/promotion/PROMOTION_RECORD.md"],
        "cognitive_pipeline":     ["ai/tokenless-agent/src/cognitive_pipeline.py"],
        "heptagon (root)":        ["heptagon/__init__.py"],
        "heptagon (agent-side)":  ["ai/tokenless-agent/src/heptagon/__init__.py"],
        "soul_manager":           ["soul_manager/soul_manager.py"],
        "memory (agent-side)":    ["ai/tokenless-agent/src/memory/__init__.py"],
        "sensory":                ["ai/tokenless-agent/src/sensory/__init__.py"],
        "governance":             ["governance/__init__.py", "governance/covenant_enforcer.py"],
        "omni-peft":              ["training/peft/__init__.py"],
    }
    findings = []
    for label, paths in surfaces.items():
        if not any((root / p).exists() for p in paths):
            findings.append(f"surface '{label}': none of {paths} exist")
    return CheckResult(
        name="engineering_surfaces_present",
        passed=not findings,
        detail="Each auditable engineering surface must have at least one source file.",
        findings=findings,
    )


def check_only_canonical_gguf_at_root(root: Path) -> CheckResult:
    gguf_dir = root / "training/gguf"
    if not gguf_dir.exists():
        return CheckResult(
            name="only_canonical_gguf_at_root",
            passed=False,
            detail="training/gguf must exist.",
            findings=[],
        )
    stray = [
        p.name for p in gguf_dir.iterdir()
        if p.is_file() and p.suffix == ".gguf" and p.name != "canonical.gguf"
    ]
    return CheckResult(
        name="only_canonical_gguf_at_root",
        passed=not stray,
        detail="At the root of training/gguf there must be exactly one .gguf — canonical.gguf.",
        findings=[f"stray .gguf at root: {s}" for s in stray],
    )


# ────────────────────────────────────────────────────────────────────────
# Driver
# ────────────────────────────────────────────────────────────────────────

CHECKS: list[Callable[[Path], CheckResult]] = [
    check_required_paths_exist,
    check_canonical_phrase_present,
    check_no_active_drift,
    check_allowlist_not_abused,
    check_canonical_sha_matches_manifest,
    check_runtime_default_points_at_canonical,
    check_no_folder_scan_for_runtime_base,
    check_only_canonical_gguf_at_root,
    check_cognitive_pipeline_single_entry,
    check_engineering_surfaces_present,
    check_depth_trace_module_present,
    check_behavioral_test_present,
]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument(
        "--root", default=None,
        help="Path to the models v7 root. Default: directory of this script's parent (so the script located at <root>/scripts/ is correct).",
    )
    ap.add_argument("--json", action="store_true", help="Emit JSON results")
    args = ap.parse_args()

    if args.root is None:
        # this script is at <root>/scripts/audit_unified_cognitive_identity.py
        root = Path(__file__).resolve().parent.parent
    else:
        root = Path(args.root).resolve()

    if not root.exists():
        print(f"ERROR: root does not exist: {root}", file=sys.stderr)
        return 2

    results = [check(root) for check in CHECKS]
    n_pass = sum(1 for r in results if r.passed)
    n_fail = sum(1 for r in results if not r.passed)

    if args.json:
        print(json.dumps({
            "root": str(root),
            "canonical_phrase": CANONICAL_PHRASE,
            "short_form": SHORT_FORM,
            "n_pass": n_pass,
            "n_fail": n_fail,
            "checks": [
                {"name": r.name, "passed": r.passed, "detail": r.detail, "findings": r.findings}
                for r in results
            ],
        }, indent=2))
    else:
        print("═══════════════════════════════════════════════════════════════════")
        print("  Unified Cognitive Identity Audit")
        print("═══════════════════════════════════════════════════════════════════")
        print(f"  Root: {root}")
        print(f"  Canonical phrase: \"{CANONICAL_PHRASE}\"")
        print(f"  Short form:       \"{SHORT_FORM}\"")
        print()
        for r in results:
            status = "PASS" if r.passed else "FAIL"
            print(f"  [{status}] {r.name}")
            print(f"         {r.detail}")
            if r.findings:
                for f in r.findings[:25]:
                    print(f"           - {f}")
                if len(r.findings) > 25:
                    print(f"           ... and {len(r.findings)-25} more")
            print()
        print(f"  Summary: {n_pass} PASS, {n_fail} FAIL")

    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
