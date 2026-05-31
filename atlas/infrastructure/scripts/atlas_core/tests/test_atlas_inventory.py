import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from atlas_inventory import build_inventory


class AtlasInventoryTests(unittest.TestCase):
    def test_inventory_contains_numbered_roots(self):
        inventory = build_inventory()["atlas_inventory"]
        self.assertIn("platform", inventory["tracked_roots"])
        self.assertIn("platform/sdlc/13_skills/active", inventory["subsystem_paths"]["skills"])


if __name__ == "__main__":
    unittest.main()
