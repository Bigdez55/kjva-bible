"""
conftest.py — pytest path setup.

Adds backend/ to sys.path so tests can `import corpus`, `from routes.complete import router`,
etc., matching how main.py imports its own modules.
"""
import sys
import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
REPO_ROOT = BACKEND_DIR.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Tests are a local development lane. If AES-GCM dependencies are unavailable,
# SoulManager may use its explicit dev-only plaintext escape hatch instead of
# silently dropping request journals.
os.environ.setdefault("TOKENLESS_SOUL_ALLOW_PLAINTEXT", "1")
os.environ.setdefault(
    "KJVA_SOUL_JOURNAL_DIR",
    str(BACKEND_DIR / "tests" / ".tmp_soul_journal"),
)
