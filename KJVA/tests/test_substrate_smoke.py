"""tests/test_substrate_smoke.py — minimal substrate smoke test.

Run: python -m pytest tests/ -q
Or:  python tests/test_substrate_smoke.py
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))


class SubstrateSmokeTest(unittest.TestCase):
    """Sanity checks on the wired substrate template."""

    def test_xmind_package_importable(self):
        """xmind_federation package imports cleanly."""
        import xmind_federation
        self.assertTrue(hasattr(xmind_federation, "XMindClient"))
        self.assertTrue(hasattr(xmind_federation, "DeliberationResult"))
        self.assertTrue(hasattr(xmind_federation, "deliberate_as"))

    def test_persona_template_exists(self):
        """The persona template file is present (for consuming projects)."""
        p = REPO_ROOT / "xmind_federation" / "personas" / "_template.txt"
        self.assertTrue(p.exists(), f"persona template missing at {p}")

    def test_xmind_client_stub_mode(self):
        """XMindClient falls back to stub when no model is reachable.

        Phase-4 added training/gguf/model.gguf to the substrate, so the
        zero-config default path now resolves to a real model. To exercise
        the stub fallback we explicitly force XMIND_MODEL to a non-existent
        path. The connection wiring must still complete cleanly and return
        a DeliberationResult with ai_powered=False.
        """
        from xmind_federation import XMindClient
        # Force missing model so we exercise the stub-fallback branch
        old = os.environ.get("XMIND_MODEL")
        os.environ["XMIND_MODEL"] = "/tmp/__definitely_not_a_model__.gguf"
        try:
            # Reset class-level singleton init flags
            XMindClient._init_done = False
            XMindClient._init_ok   = False
            c = XMindClient(member_name="smoke-test-member")
            r = c.deliberate(domain="test", context="ctx", question="ok?")
            self.assertFalse(r.ai_powered, "should be in stub mode without weights")
            self.assertEqual(r.member, "smoke-test-member")
        finally:
            if old is None:
                os.environ.pop("XMIND_MODEL", None)
            else:
                os.environ["XMIND_MODEL"] = old
            XMindClient._init_done = False
            XMindClient._init_ok   = False

    def test_lazy_imports_present(self):
        """Top-level __init__.py exposes the lazy accessors."""
        # Load REPO_ROOT/__init__.py EXPLICITLY by path. The bare `import __init__`
        # is ambiguous under pytest collection (any __init__ on sys.path may win),
        # which breaks when the substrate is deployed flat (e.g. as the KJVA root).
        import importlib.util
        init_path = REPO_ROOT / "__init__.py"
        spec = importlib.util.spec_from_file_location("_substrate_root_init", init_path)
        substrate = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(substrate)
        for accessor in ("get_harness", "get_layers", "get_covenant_enforcer",
                          "get_decision_envelope", "get_soul_manager"):
            self.assertTrue(hasattr(substrate, accessor),
                              f"substrate missing {accessor}")

    def test_training_scripts_executable(self):
        """training/scripts/* are executable."""
        for s in ("wire_all.sh", "npz_to_safetensors.py"):
            p = REPO_ROOT / "training" / "scripts" / s
            self.assertTrue(p.exists(), f"missing: {p}")
            self.assertTrue(os.access(p, os.X_OK), f"not executable: {p}")

    def test_makefile_present(self):
        """ai/xmind/Makefile exists."""
        m = REPO_ROOT / "ai" / "xmind" / "Makefile"
        self.assertTrue(m.exists(), f"missing: {m}")

    def test_canonical_blueprints_intact(self):
        """The 8 SUPER C blueprints must still be present."""
        blueprints = [
            "soul_manager/soul_manager.sc",
            "heptagon/heptagon.sc",
            "ai/tokenless_agent.sc",
            "governance/governance.sc",
            "ai/tts/tts_engine.sc",
            "ai/companion/companion.sc",
            "ai/xmind/superc/xmind_core.sc",
            "ai/xmind/superc/xmind_evolved.sc",
        ]
        for bp in blueprints:
            self.assertTrue((REPO_ROOT / bp).exists(),
                              f"blueprint missing: {bp}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
