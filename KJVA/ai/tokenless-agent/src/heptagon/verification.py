"""ai/tokenless-agent/src/heptagon/verification.py
ResponseVerifier — Heptagon Layer 5 (Evaluation) output quality and safety gate.

Checks:
  1. Safety   — regex patterns for 8 harmful content categories (halt if failed)
  2. Relevance — keyword overlap between query and response
  3. Coherence — response structural quality (length, sentences, repetition)
  4. Completeness — response addresses key query terms

Halt conditions:
  - safety_fail    → score forced to 0.0, passed=False
  - score < 0.3    → passed=False
  - coherence < 0.5 → passed=False
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger("tokenless.heptagon.verification")

# ── Safety patterns (8 categories) ───────────────────────────────────────────
# These patterns target obvious harmful output indicators, not topic discussion.

_SAFETY_PATTERNS: List[Tuple[str, re.Pattern]] = [
    ("violence_instructions", re.compile(
        r"\b(step.by.step.*(?:kill|harm|attack|bomb|weapon)|"
        r"how to (?:make|build|assemble).*(?:bomb|explosive|weapon))\b",
        re.IGNORECASE | re.DOTALL,
    )),
    ("pii_leak", re.compile(
        r"\b\d{3}-\d{2}-\d{4}\b|"                    # SSN
        r"\b(?:\d{4}[- ]){3}\d{4}\b|"                # credit card
        r"\b[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}\b",  # email in output
        re.IGNORECASE,
    )),
    ("malware_code", re.compile(
        r"(?:import\s+subprocess|os\.system|exec\(|eval\(|__import__)"
        r".*(?:rm\s+-rf|del\s+/f|format\s+c:)",
        re.IGNORECASE | re.DOTALL,
    )),
    ("self_harm", re.compile(
        r"\b(instructions for|guide to|how to).*(?:self.harm|suicide|overdose)\b",
        re.IGNORECASE,
    )),
    ("hate_speech_generation", re.compile(
        r"\b(write|generate|create|draft).*\b(slur|racist|sexist|bigot)\b.*content\b",
        re.IGNORECASE,
    )),
    ("credential_exposure", re.compile(
        r"\b(password|api.?key|secret.?key|access.?token)\s*[:=]\s*['\"]?[A-Za-z0-9+/=_\-]{8,}",
        re.IGNORECASE,
    )),
    ("prompt_injection", re.compile(
        r"(?:ignore previous instructions|disregard all prior|"
        r"act as (?:DAN|jailbreak)|you are now (?:DAN|unrestricted))",
        re.IGNORECASE,
    )),
    ("csam_indicators", re.compile(
        r"\b(child|minor|underage).*\b(explicit|nude|sexual|pornograph)\b",
        re.IGNORECASE,
    )),
]

# ── Thresholds ────────────────────────────────────────────────────────────────
_HALT_SCORE: float = 0.3
_HALT_COHERENCE: float = 0.5
_MIN_RESPONSE_CHARS: int = 10
_MAX_RESPONSE_CHARS: int = 32768   # guard against runaway generation


# ── VerificationResult ────────────────────────────────────────────────────────

@dataclass
class VerificationResult:
    """Output of ResponseVerifier.verify()."""
    passed: bool
    score: float                      # overall 0.0 – 1.0
    flags: List[str] = field(default_factory=list)
    safety_passed: bool = True
    relevance_score: float = 0.0
    coherence_score: float = 0.0
    completeness_score: float = 0.0
    triggered_category: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "score": round(self.score, 4),
            "flags": self.flags,
            "safety_passed": self.safety_passed,
            "relevance_score": round(self.relevance_score, 4),
            "coherence_score": round(self.coherence_score, 4),
            "completeness_score": round(self.completeness_score, 4),
            "triggered_category": self.triggered_category,
        }


# ── ResponseVerifier ──────────────────────────────────────────────────────────

class ResponseVerifier:
    """
    Heptagon Layer 5 evaluation gate.

    verify(query, response) returns a VerificationResult.
    The caller (ReviewingState handler) should halt generation if
    result.passed is False.

    Scoring weights:
      relevance    40%
      coherence    35%
      completeness 25%
    """

    _W_RELEVANCE: float = 0.40
    _W_COHERENCE: float = 0.35
    _W_COMPLETENESS: float = 0.25

    def __init__(self) -> None:
        logger.debug("ResponseVerifier: initialised with %d safety categories", len(_SAFETY_PATTERNS))

    # ── Public API ────────────────────────────────────────────────────────────

    def verify(self, query: str, response: str) -> VerificationResult:
        """
        Run all checks and return a VerificationResult.

        Halt immediately on safety failure (score = 0.0, passed = False).
        """
        flags: List[str] = []

        # 1. Safety check — halt immediately on any match
        safety_ok, triggered = self._check_safety(response)
        if not safety_ok:
            logger.warning(
                "ResponseVerifier: SAFETY HALT — category=%s", triggered
            )
            return VerificationResult(
                passed=False,
                score=0.0,
                flags=["safety_halt"],
                safety_passed=False,
                triggered_category=triggered,
            )

        # 2. Component checks
        rel = self._check_relevance(query, response)
        coh = self._check_coherence(response)
        comp = self._check_completeness(query, response)

        # Weighted composite score
        score = (
            rel  * self._W_RELEVANCE +
            coh  * self._W_COHERENCE +
            comp * self._W_COMPLETENESS
        )
        score = max(0.0, min(1.0, score))

        if rel < 0.2:
            flags.append("low_relevance")
        if coh < _HALT_COHERENCE:
            flags.append("low_coherence")
        if comp < 0.2:
            flags.append("low_completeness")
        if score < _HALT_SCORE:
            flags.append("score_below_threshold")

        passed = (
            safety_ok
            and score >= _HALT_SCORE
            and coh >= _HALT_COHERENCE
        )

        result = VerificationResult(
            passed=passed,
            score=score,
            flags=flags,
            safety_passed=True,
            relevance_score=rel,
            coherence_score=coh,
            completeness_score=comp,
        )
        logger.debug(
            "ResponseVerifier: passed=%s score=%.3f rel=%.3f coh=%.3f comp=%.3f flags=%s",
            passed, score, rel, coh, comp, flags,
        )
        return result

    # ── Safety ────────────────────────────────────────────────────────────────

    def _check_safety(self, response: str) -> Tuple[bool, Optional[str]]:
        """Test all 8 safety patterns. Returns (ok, triggered_category)."""
        for category, pattern in _SAFETY_PATTERNS:
            if pattern.search(response):
                return False, category
        return True, None

    # ── Relevance ─────────────────────────────────────────────────────────────

    def _check_relevance(self, query: str, response: str) -> float:
        """
        Token overlap between query and response (Jaccard-style).
        Score in [0.0, 1.0]. Short responses penalised if length < minimum.
        """
        if len(response) < _MIN_RESPONSE_CHARS:
            return 0.1  # trivially short
        query_tokens = _word_set(query)
        resp_tokens = _word_set(response)
        if not query_tokens:
            return 0.5  # no query to compare against
        overlap = len(query_tokens & resp_tokens)
        union = len(query_tokens | resp_tokens)
        if union == 0:
            return 0.0
        # Boost score if most query terms appear in response
        coverage = overlap / len(query_tokens)
        jaccard = overlap / union
        return min(1.0, 0.6 * coverage + 0.4 * jaccard)

    # ── Coherence ─────────────────────────────────────────────────────────────

    def _check_coherence(self, response: str) -> float:
        """
        Structural quality heuristics:
          - Length penalty for very short or very long responses
          - Sentence count (≥1 full sentence required)
          - Repetition penalty (repeated 4-gram ratio)
        Score in [0.0, 1.0].
        """
        n = len(response)
        if n < _MIN_RESPONSE_CHARS:
            return 0.0

        # Length score: sigmoid-like centred around 200-2000 chars
        length_score: float
        if n < 20:
            length_score = 0.1
        elif n < 50:
            length_score = 0.4
        elif n > _MAX_RESPONSE_CHARS:
            length_score = 0.4
        else:
            length_score = 1.0

        # Sentence completeness: contains at least one sentence-ending punctuation
        has_sentence = bool(re.search(r'[.!?]', response))
        sentence_score = 1.0 if has_sentence else 0.5

        # Repetition: compute 4-gram repetition ratio
        rep_score = 1.0 - _repetition_ratio(response, n_gram=4)

        score = 0.35 * length_score + 0.35 * sentence_score + 0.30 * rep_score
        return max(0.0, min(1.0, score))

    # ── Completeness ──────────────────────────────────────────────────────────

    def _check_completeness(self, query: str, response: str) -> float:
        """
        Check that interrogative-intent query terms are addressed.
        Identifies wh-question words and key nouns; scores coverage.
        """
        query_lower = query.lower()
        resp_lower = response.lower()

        # Extract content words from query (skip stopwords)
        content_words = [
            w for w in _word_set(query)
            if w not in _STOPWORDS and len(w) > 3
        ]
        if not content_words:
            return 0.7  # no content words to check against

        covered = sum(1 for w in content_words if w in resp_lower)
        return min(1.0, covered / len(content_words))


# ── Text utilities ────────────────────────────────────────────────────────────

_STOPWORDS: Set[str] = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "can", "need", "dare", "ought",
    "used", "what", "when", "where", "who", "which", "how", "why", "that",
    "this", "these", "those", "with", "from", "into", "about", "then",
    "than", "their", "there", "here", "your", "our", "its", "and", "but",
    "for", "not", "also", "just", "more", "some", "such", "each", "only",
}


def _word_set(text: str) -> Set[str]:
    return set(re.findall(r"\b[a-z]{2,}\b", text.lower()))


def _repetition_ratio(text: str, n_gram: int = 4) -> float:
    """
    Compute the fraction of repeated n-grams.
    Returns 0.0 (no repetition) to 1.0 (entirely repeated).
    """
    words = text.lower().split()
    if len(words) < n_gram * 2:
        return 0.0
    grams: List[str] = []
    for i in range(len(words) - n_gram + 1):
        grams.append(" ".join(words[i: i + n_gram]))
    if not grams:
        return 0.0
    unique = len(set(grams))
    return 1.0 - (unique / len(grams))
