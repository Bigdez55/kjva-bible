"""
conftest.py — pytest path setup.

Adds backend/ to sys.path so tests can `import corpus`, `from routes.complete import router`,
etc., matching how main.py imports its own modules.
"""
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
