"""test_no_archive_taxonomy_import.py — ADR-0002 §13: "docs/_archive is treated as reference-only."

The active runtime must not import code or taxonomy from archived/reference material. This greps
the live runtime source for imports of an `_archive` path. (Persona/Council taxonomy in active
runtime is a separate neutral-taxonomy concern; here we pin the archive-import rule.)

Run:  python3 -m pytest tests/test_no_archive_taxonomy_import.py -q
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNTIME = ROOT / "ai" / "tokenless-agent" / "src"

_ARCHIVE_IMPORT = re.compile(r"(import\s+\S*_archive|from\s+\S*_archive\s+import)")


def test_no_archive_imports_in_runtime():
    offenders = []
    for p in RUNTIME.rglob("*.py"):
        for i, line in enumerate(p.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
            if _ARCHIVE_IMPORT.search(line):
                offenders.append(f"{p.relative_to(ROOT)}:{i}: {line.strip()}")
    assert not offenders, "runtime imports from _archive (reference-only):\n" + "\n".join(offenders)
