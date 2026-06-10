"""
peft/fingerprint.py — Task and Domain Fingerprinter

Converts user-supplied task/domain description into a TaskFingerprint that
the PEFT Compiler uses to select appropriate adaptation methods.

Inputs:  task description string, data size estimate, domain keywords, hardware budget
Output:  TaskFingerprint with recommended adaptation profile
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from .base import HardwareBudget


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class DataSize(Enum):
    TINY       = "tiny"        # < 500 examples
    SMALL      = "small"       # 500 – 5k examples
    MEDIUM     = "medium"      # 5k – 50k examples
    LARGE      = "large"       # 50k – 500k examples
    VERY_LARGE = "very_large"  # > 500k examples


class DomainShift(Enum):
    NONE      = 0
    LOW       = 1
    MEDIUM    = 2
    HIGH      = 3
    VERY_HIGH = 4


# ---------------------------------------------------------------------------
# Task fingerprint
# ---------------------------------------------------------------------------

@dataclass
class TaskFingerprint:
    task_description: str
    domains: list[str]
    tasks: list[str]
    data_size: DataSize
    domain_shift: DomainShift
    reasoning_requirement: str   # "low", "medium", "high"
    style_requirement: str
    tool_use_requirement: str
    recommended_substrate: str   # "qlora", "lora", "ia3", "prefix", "sft"
    recommended_peft_stack: list[str]


# ---------------------------------------------------------------------------
# Keyword tables
# ---------------------------------------------------------------------------

_REASONING_KEYWORDS = {
    "high": ["chain-of-thought", "cot", "reasoning", "math", "logic", "proof", "theorem",
             "arithmetic", "analysis", "deduce", "infer", "argument"],
    "medium": ["explain", "summarize", "compare", "evaluate", "classify", "extract"],
    "low": ["translate", "paraphrase", "rewrite", "generate", "complete", "fill"],
}

_STYLE_KEYWORDS = {
    "high": ["style", "tone", "voice", "creative", "poetry", "narrative", "literary",
             "write like", "persona", "character", "roleplay"],
    "medium": ["formal", "casual", "professional", "friendly", "concise", "detailed"],
    "low": ["answer", "respond", "output", "return", "produce"],
}

_TOOL_KEYWORDS = {
    "high": ["tool", "function call", "api", "search", "calculator", "code", "execute",
             "plugin", "action", "retrieval", "browse"],
    "medium": ["lookup", "query", "fetch", "retrieve"],
    "low": [],
}

_DOMAIN_SHIFT_KEYWORDS = {
    DomainShift.VERY_HIGH: ["medical", "legal", "scientific", "biomedical", "chemistry",
                            "physics", "financial", "clinical", "pharmaceutical"],
    DomainShift.HIGH:      ["technical", "engineering", "programming", "coding", "scripture",
                            "theological", "biblical", "academic", "research"],
    DomainShift.MEDIUM:    ["business", "customer service", "education", "support", "news"],
    DomainShift.LOW:       ["general", "conversational", "chat", "informal"],
    DomainShift.NONE:      [],
}

_TASK_KEYWORDS = {
    "summarization": ["summarize", "summary", "abstract", "tldr", "condense"],
    "classification": ["classify", "label", "categorize", "tag", "detect"],
    "generation": ["generate", "write", "create", "compose", "produce"],
    "qa": ["question", "answer", "qa", "quiz", "faq"],
    "translation": ["translate", "translation", "language pair"],
    "extraction": ["extract", "parse", "retrieve", "identify", "find"],
    "reasoning": ["reason", "logic", "deduce", "solve", "proof"],
    "coding": ["code", "program", "function", "debug", "implement"],
    "dialogue": ["chat", "conversation", "dialogue", "roleplay"],
}


# ---------------------------------------------------------------------------
# Fingerprinter
# ---------------------------------------------------------------------------

class TaskFingerprinter:
    """Convert a task description into a TaskFingerprint."""

    def fingerprint(
        self,
        task_desc: str,
        domains: list[str],
        data_size: DataSize,
        hardware: HardwareBudget,
    ) -> TaskFingerprint:
        text = (task_desc + " " + " ".join(domains)).lower()

        # Detect tasks from keywords
        detected_tasks = self._detect_tasks(text)

        # Estimate domain shift
        domain_shift = self._estimate_domain_shift(text)

        # Estimate requirements
        reasoning = self._level(text, _REASONING_KEYWORDS)
        style = self._level(text, _STYLE_KEYWORDS)
        tool_use = self._level(text, _TOOL_KEYWORDS)

        # Select substrate and PEFT stack
        substrate, stack = self._select_stack(
            data_size, domain_shift, hardware, reasoning, style
        )

        return TaskFingerprint(
            task_description=task_desc,
            domains=domains,
            tasks=detected_tasks,
            data_size=data_size,
            domain_shift=domain_shift,
            reasoning_requirement=reasoning,
            style_requirement=style,
            tool_use_requirement=tool_use,
            recommended_substrate=substrate,
            recommended_peft_stack=stack,
        )

    # ------------------------------------------------------------------
    # Selection logic — escalation ladder
    # ------------------------------------------------------------------

    def _select_stack(
        self,
        data_size: DataSize,
        domain_shift: DomainShift,
        hardware: HardwareBudget,
        reasoning: str,
        style: str,
    ) -> tuple[str, list[str]]:
        """Apply the escalation ladder and return (substrate, peft_stack)."""

        # Substrate: always qlora if VRAM < 8 GB
        if hardware.train_vram_mb < 8_000:
            substrate = "qlora"
        else:
            substrate = "float16"

        # PEFT stack selection based on domain_shift + data_size.
        #
        # "cheapest sufficient change" doctrine: lower shift → lighter methods.
        # bitfit is intentionally included at NONE and LOW so LayerNorm calibration
        # is possible via the compiler's bitfit recommendation for those layers.
        if data_size == DataSize.TINY and domain_shift in (DomainShift.NONE, DomainShift.LOW):
            stack = ["prefix", "ia3", "bitfit"]
        elif domain_shift == DomainShift.NONE:
            stack = ["ia3", "bitfit"]
        elif domain_shift == DomainShift.LOW:
            stack = ["ia3", "lora", "bitfit"]
        elif domain_shift == DomainShift.MEDIUM:
            stack = ["lora", "adalora", "ia3"]
        elif domain_shift == DomainShift.HIGH:
            stack = ["lora", "adalora", "dora"]
        else:  # VERY_HIGH
            stack = ["dora", "adalora", "houlsby_adapter"]

        # Escalate if reasoning is high and stack doesn't already include strong methods
        if reasoning == "high" and "dora" not in stack and "adalora" not in stack:
            stack.append("adalora")

        # Always include substrate override
        if substrate == "qlora" and "qlora" not in stack:
            stack = ["qlora"] + stack

        return substrate, stack

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _detect_tasks(self, text: str) -> list[str]:
        found: list[str] = []
        for task_name, kws in _TASK_KEYWORDS.items():
            if any(kw in text for kw in kws):
                found.append(task_name)
        return found or ["general"]

    def _estimate_domain_shift(self, text: str) -> DomainShift:
        for shift_level in (
            DomainShift.VERY_HIGH,
            DomainShift.HIGH,
            DomainShift.MEDIUM,
            DomainShift.LOW,
        ):
            if any(kw in text for kw in _DOMAIN_SHIFT_KEYWORDS[shift_level]):
                return shift_level
        return DomainShift.NONE

    def _level(self, text: str, keyword_table: dict[str, list[str]]) -> str:
        for level in ("high", "medium", "low"):
            if any(kw in text for kw in keyword_table.get(level, [])):
                return level
        return "low"
