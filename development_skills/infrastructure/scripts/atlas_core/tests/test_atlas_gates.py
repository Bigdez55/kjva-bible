import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from atlas_gates import SAFE_GATES, UNSAFE_SKIPPED


class AtlasGateTests(unittest.TestCase):
    def test_safe_gates_are_check_mode(self):
        commands = [" ".join(g.command) for g in SAFE_GATES]
        self.assertTrue(any("sync_registries.py --check" in c for c in commands))
        self.assertTrue(any("check_truth_drift.py --check --no-write" in c for c in commands))
        self.assertTrue(any("git diff --check" in c for c in commands))

    def test_unsafe_rebuild_ledger_skipped(self):
        skipped = " ".join(item["command"] for item in UNSAFE_SKIPPED)
        self.assertIn("rebuild_master_ledger.py", skipped)


if __name__ == "__main__":
    unittest.main()
