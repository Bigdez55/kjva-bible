import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from atlas_inventory import build_inventory


class AtlasInventoryTests(unittest.TestCase):
    def test_inventory_contains_numbered_roots(self):
        inventory = build_inventory()["atlas_inventory"]
        self.assertGreaterEqual(inventory["tracked_numbered_roots_count"], 45)
        self.assertIn("13_skills", inventory["tracked_numbered_roots"])


if __name__ == "__main__":
    unittest.main()
