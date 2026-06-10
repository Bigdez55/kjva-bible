from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, List


@dataclass
class TokenTrace:
    """Per-token generation trace for post-inference attestation."""
    token_count: int = 0
    byte_count: int = 0
    max_new: int = 96
    temperature: float = 0.0
    stopped_by: str = "max_new"  # "max_new" | "eos" | "governance"


@dataclass
class GenerationStatus:
    """Status of the generation call."""
    engine_loaded: bool = False
    weights_path: Optional[str] = None
    stub_mode: bool = True  # True when XMIND unavailable
    error: Optional[str] = None


@dataclass
class OutputCandidate:
    """Structured return from inference engine — ADR-0002 §4.5 Edge E."""
    text: Optional[str] = None
    token_trace: TokenTrace = field(default_factory=TokenTrace)
    generation_status: GenerationStatus = field(default_factory=GenerationStatus)

    def __str__(self) -> str:
        return self.text or ""

    def __bool__(self) -> bool:
        return bool(self.text)

    def to_dict(self) -> dict:
        import dataclasses
        return dataclasses.asdict(self)
