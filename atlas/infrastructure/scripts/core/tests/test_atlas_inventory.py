import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from atlas_inventory import build_inventory


class AtlasInventoryTests(unittest.TestCase):
    def test_inventory_contains_numbered_roots(self):
        inventory = build_inventory()["atlas_inventory"]
        self.assertGreaterEqual(inventory["tracked_numbered_roots_count"], 45)
        # Post-restructure the numbered SDLC dirs live under platform/sdlc/.
        self.assertIn("platform/sdlc/13_skills", inventory["tracked_numbered_roots"])


if __name__ == "__main__":
    unittest.main()
