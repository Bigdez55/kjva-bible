import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from atlas_status import build_status


class AtlasStatusTests(unittest.TestCase):
    def test_status_shape(self):
        status = build_status()["atlas_status"]
        self.assertEqual(status["system_name"], "SUPER C Atlas")
        self.assertEqual(status["repository_lineage"], "Development_Skills")
        self.assertIn("bookworm", status["subsystems"])
        self.assertIn("validation", status["subsystems"])


if __name__ == "__main__":
    unittest.main()
