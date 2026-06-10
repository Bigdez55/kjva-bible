"""tests/test_unified_cognitive_identity.py — pytest gate for the Unified
Cognitive Identity Contract.

These tests fail HARD on doctrine drift, on a broken-promotion state, on
folder-scan resolution of the canonical runtime base, and on missing
engineering surfaces. They are the contract that the assistant CANNOT
declare "the architecture is built" without passing.

Run:
    python -m pytest tests/test_unified_cognitive_identity.py -v

These tests intentionally do NOT exercise the C engine — that is the job
of validate_apex.py. Here we verify:

    1. Doctrine on disk is intact (canonical phrase, no active drift).
    2. Promotion artifacts are present and SHA-consistent.
    3. Runtime defaults resolve to training/gguf/canonical.gguf.
    4. CognitivePipeline has a single fused entry.
    5. Each named engineering surface has a source file.
    6. Only one .gguf lives at the root of training/gguf/.
"""
from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

AUDIT_SCRIPT = REPO_ROOT / "scripts" / "audit_unified_cognitive_identity.py"

CANONICAL_PHRASE = (
    "Identity is singular. Engineering surfaces remain auditable. "
    "Cognitive flow remains fused."
)


class UnifiedCognitiveIdentityGate(unittest.TestCase):
    """Hard gate. Every check below must pass."""

    # ── 1. Audit script returns 0 ────────────────────────────────────

    def test_01_audit_script_passes(self):
        """The audit script must exit 0 — no doctrine drift found."""
        self.assertTrue(AUDIT_SCRIPT.exists(),
                        f"Audit script missing: {AUDIT_SCRIPT}")
        result = subprocess.run(
            [sys.executable, str(AUDIT_SCRIPT)],
            capture_output=True, text=True, cwd=str(REPO_ROOT),
        )
        self.assertEqual(
            result.returncode, 0,
            f"audit_unified_cognitive_identity.py FAILED\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )

    # ── 2. Canonical phrase verbatim in doctrine doc ─────────────────

    def test_02_canonical_phrase_in_doctrine(self):
        doc = REPO_ROOT / "training" / "gguf" / "CANONICAL_BASE_DOCTRINE.md"
        self.assertTrue(doc.exists(), f"missing: {doc}")
        self.assertIn(CANONICAL_PHRASE, doc.read_text(encoding="utf-8"),
                      "canonical doctrine phrase missing from CANONICAL_BASE_DOCTRINE.md")

    # ── 3. Canonical GGUF SHA matches manifest ───────────────────────

    def test_03_canonical_sha_matches_manifest(self):
        import hashlib
        gguf = REPO_ROOT / "training" / "gguf" / "canonical.gguf"
        man  = REPO_ROOT / "training" / "gguf" / "promotion" / "lineage_manifest.json"
        self.assertTrue(gguf.exists(), f"missing: {gguf}")
        self.assertTrue(man.exists(),  f"missing: {man}")
        manifest = json.loads(man.read_text())
        expected = manifest.get("canonical", {}).get("sha256", "")
        h = hashlib.sha256()
        with gguf.open("rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        self.assertEqual(h.hexdigest(), expected,
                         "canonical.gguf SHA-256 does not match lineage_manifest.json")

    # ── 4. Runtime default points at canonical.gguf ──────────────────

    def test_04_runtime_default_canonical(self):
        candidates = [
            REPO_ROOT / "xmind_federation" / "client.py",
            REPO_ROOT / "_xmind" / "client.py",
        ]
        found_any = False
        for c in candidates:
            if c.exists():
                found_any = True
                text = c.read_text(encoding="utf-8")
                self.assertIn(
                    "canonical.gguf", text,
                    f"{c.relative_to(REPO_ROOT)} does not reference canonical.gguf"
                )
        self.assertTrue(found_any,
            "No XMindClient file found at xmind_federation/client.py or _xmind/client.py")

    # ── 5. Exactly one .gguf at root of training/gguf/ ───────────────

    def test_05_only_canonical_at_root(self):
        gguf_dir = REPO_ROOT / "training" / "gguf"
        self.assertTrue(gguf_dir.exists(), f"missing: {gguf_dir}")
        ggufs = [p for p in gguf_dir.iterdir() if p.is_file() and p.suffix == ".gguf"]
        names = sorted(p.name for p in ggufs)
        self.assertEqual(
            names, ["canonical.gguf"],
            f"Only canonical.gguf may live at root of training/gguf/; found: {names}"
        )

    # ── 6. CognitivePipeline single fused entry ──────────────────────

    def test_06_cognitive_pipeline_single_entry(self):
        p = REPO_ROOT / "ai" / "tokenless-agent" / "src" / "cognitive_pipeline.py"
        self.assertTrue(p.exists(), f"missing: {p}")
        text = p.read_text(encoding="utf-8")
        self.assertIn("class CognitivePipeline", text)
        self.assertIn("def get_pipeline", text)
        self.assertIn("async def execute", text)

    # ── 7. Engineering surfaces present (not separate identities) ────

    def test_07_engineering_surfaces_exist(self):
        surfaces = {
            "architecture (xmind)":  ["ai/xmind/include/xmind.h", "ai/xmind/src/interp_tokenless.c"],
            "promotion":             ["training/gguf/canonical.gguf",
                                       "training/gguf/promotion/PROMOTION_RECORD.md"],
            "cognitive_pipeline":    ["ai/tokenless-agent/src/cognitive_pipeline.py"],
            "heptagon (root)":       ["heptagon/__init__.py"],
            "heptagon (agent-side)": ["ai/tokenless-agent/src/heptagon/__init__.py"],
            "soul_manager":          ["soul_manager/soul_manager.py"],
            "memory (agent-side)":   ["ai/tokenless-agent/src/memory/__init__.py"],
            "sensory":               ["ai/tokenless-agent/src/sensory/__init__.py"],
            "governance":            ["governance/__init__.py", "governance/covenant_enforcer.py"],
            "omni-peft":             ["training/peft/__init__.py"],
        }
        missing_surfaces: list[str] = []
        for label, paths in surfaces.items():
            if not any((REPO_ROOT / pth).exists() for pth in paths):
                missing_surfaces.append(label)
        self.assertEqual(missing_surfaces, [],
            f"engineering surfaces missing source files: {missing_surfaces}")

    # ── 8. No folder-scan logic for runtime base ─────────────────────

    def test_08_no_folder_scan_for_runtime_base(self):
        import re
        offenders: list[str] = []
        for rel in [
            "xmind_federation/client.py",
            "_xmind/client.py",
            "ai/tokenless-agent/src/cognitive_pipeline.py",
            "ai/tokenless-agent/src/agent.py",
        ]:
            p = REPO_ROOT / rel
            if not p.exists():
                continue
            text = p.read_text(encoding="utf-8")
            for pat, label in [
                (r'glob\s*\(\s*["\'][^"\']*\.gguf', "glob(*.gguf)"),
                (r'sorted\s*\([^)]*\.gguf',          "sorted(...gguf)"),
                (r'os\.listdir\s*\([^)]*gguf',       "listdir(gguf...)"),
            ]:
                for lineno, line in enumerate(text.splitlines(), start=1):
                    if re.search(pat, line):
                        offenders.append(f"{rel}:{lineno}: {label} — {line.strip()[:120]}")
        self.assertEqual(offenders, [],
            f"Folder-scan resolution of canonical base detected: {offenders}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
