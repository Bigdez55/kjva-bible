"""test_no_direct_memory_write_from_adapter.py — ADR-0002 §9.2 rule 5: "No adapter writes memory directly."

Adapters (PEFT operators) must return tensors/deltas only — never write the memory store. This is
enforced by construction (the operator layer has no memory-write API). This test pins that: no PEFT
operator module imports the memory package or calls a writeback/memory-write API.

Run:  python3 -m pytest tests/test_no_direct_memory_write_from_adapter.py -q
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PEFT = ROOT / "training" / "peft"

_MEM_WRITE = re.compile(
    r"(from\s+(memory|soul_manager)\b|import\s+(memory|soul_manager)\b|"
    r"\.writeback\(|\.register\(\s*ExperienceAtom|lifespan_ledger|\.put\(\s*['\"]mem)"
)


def test_no_peft_operator_writes_memory():
    offenders = []
    for p in PEFT.rglob("*.py"):
        for i, line in enumerate(p.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
            if _MEM_WRITE.search(line):
                offenders.append(f"{p.relative_to(ROOT)}:{i}: {line.strip()}")
    assert not offenders, ("PEFT/adapter layer writes memory directly (§9.2 rule 5):\n"
                           + "\n".join(offenders))
