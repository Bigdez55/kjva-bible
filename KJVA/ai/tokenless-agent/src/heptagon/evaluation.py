"""ai/tokenless-agent/src/heptagon/evaluation.py
CycleEvaluator + QualityTracker — Heptagon Layer 5 (Evaluation) per-cycle
quality assessment across AI response history.

Unlike verification.py (which gates individual responses with pass/fail),
evaluation.py tracks quality ACROSS cycles and detects drift, degradation,
and systematic failure patterns.  It replaces the manual Guardian Sentinel
quality-monitoring process with automated per-cycle statistical checks.

Key metrics per cycle:
  relevance, coherence, completeness, user_satisfaction,
  latency_ms, tokens_used, tool_calls, errors

Drift detection:
  Rolling-window comparison against a baseline window.
  Alert if quality drops by more than ALERT_THRESHOLD (15%).
"""
from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Set

logger = logging.getLogger("tokenless.heptagon.evaluation")

# ── Stopwords (shared with verification.py logic) ────────────────────────────

_STOPWORDS: Set[str] = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "can", "need", "dare", "ought",
    "used", "what", "when", "where", "who", "which", "how", "why", "that",
    "this", "these", "those", "with", "from", "into", "about", "then",
    "than", "their", "there", "here", "your", "our", "its", "and", "but",
    "for", "not", "also", "just", "more", "some", "such", "each", "only",
}

_MIN_RESPONSE_CHARS: int = 10
_MAX_RESPONSE_CHARS: int = 32768


# ── EvaluationMetrics ────────────────────────────────────────────────────────

@dataclass
class EvaluationMetrics:
    """Quality snapshot for a single AI response cycle."""

    cycle_id: int
    timestamp: float
    relevance_score: float       # 0.0 – 1.0
    coherence_score: float       # 0.0 – 1.0
    completeness_score: float    # 0.0 – 1.0
    user_satisfaction: float     # 0.0 – 1.0  (inferred from follow-up actions)
    latency_ms: float
    tokens_used: int
    tool_calls: int
    errors: int

    # ── Scoring weights (match verification.py) ──────────────────────────────
    _W_RELEVANCE: float = field(default=0.30, repr=False)
    _W_COHERENCE: float = field(default=0.25, repr=False)
    _W_COMPLETENESS: float = field(default=0.20, repr=False)
    _W_SATISFACTION: float = field(default=0.25, repr=False)

    @property
    def composite_score(self) -> float:
        """Weighted composite across all quality dimensions."""
        raw = (
            self.relevance_score * self._W_RELEVANCE
            + self.coherence_score * self._W_COHERENCE
            + self.completeness_score * self._W_COMPLETENESS
            + self.user_satisfaction * self._W_SATISFACTION
        )
        return max(0.0, min(1.0, raw))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cycle_id": self.cycle_id,
            "timestamp": self.timestamp,
            "relevance": round(self.relevance_score, 4),
            "coherence": round(self.coherence_score, 4),
            "completeness": round(self.completeness_score, 4),
            "satisfaction": round(self.user_satisfaction, 4),
            "composite": round(self.composite_score, 4),
            "latency_ms": round(self.latency_ms, 1),
            "tokens_used": self.tokens_used,
            "tool_calls": self.tool_calls,
            "errors": self.errors,
        }


# ── QualityTracker ───────────────────────────────────────────────────────────

class QualityTracker:
    """Rolling-window quality tracker — detects drift and degradation.

    Maintains a history of EvaluationMetrics and compares the most recent
    WINDOW_SIZE cycles against the baseline (the first WINDOW_SIZE cycles
    recorded).  Alerts when quality drops more than ALERT_THRESHOLD from
    the established baseline.
    """

    WINDOW_SIZE: int = 100
    ALERT_THRESHOLD: float = 0.15   # 15 percentage-point drop triggers alert

    def __init__(self) -> None:
        self.history: List[EvaluationMetrics] = []
        self._baseline_locked: bool = False
        self._baseline_score: float = 0.0
        self.alert_callbacks: List[Callable[[Dict[str, Any]], None]] = []
        logger.debug(
            "QualityTracker: initialised (window=%d, threshold=%.2f)",
            self.WINDOW_SIZE, self.ALERT_THRESHOLD,
        )

    # ── Recording ────────────────────────────────────────────────────────────

    def record(self, metrics: EvaluationMetrics) -> None:
        """Append metrics and lock baseline once first window is full."""
        self.history.append(metrics)
        # Lock baseline once we have enough data
        if not self._baseline_locked and len(self.history) >= self.WINDOW_SIZE:
            self._baseline_score = self._mean_composite(
                self.history[: self.WINDOW_SIZE]
            )
            self._baseline_locked = True
            logger.info(
                "QualityTracker: baseline locked at %.4f over %d cycles",
                self._baseline_score, self.WINDOW_SIZE,
            )
        # Check for drift alert
        if self._baseline_locked and self.drift_detected():
            self._fire_alert()

    # ── Quality queries ──────────────────────────────────────────────────────

    def current_quality(self) -> float:
        """Weighted average composite score over the last WINDOW_SIZE cycles."""
        if not self.history:
            return 0.0
        window = self.history[-self.WINDOW_SIZE:]
        return self._mean_composite(window)

    def baseline_quality(self) -> float:
        """Composite score of the first WINDOW_SIZE cycles (or all if fewer)."""
        if self._baseline_locked:
            return self._baseline_score
        if not self.history:
            return 0.0
        return self._mean_composite(
            self.history[: self.WINDOW_SIZE]
        )

    def drift_detected(self) -> bool:
        """True if current quality is more than ALERT_THRESHOLD below baseline."""
        if not self._baseline_locked:
            return False
        return (self._baseline_score - self.current_quality()) > self.ALERT_THRESHOLD

    def degradation_rate(self) -> float:
        """Linear regression slope of composite scores over time.

        Returns change-per-cycle.  Negative slope = degradation.
        Returns 0.0 if fewer than 2 data points.
        """
        n = len(self.history)
        if n < 2:
            return 0.0
        # Simple OLS slope: sum((x - x_mean)(y - y_mean)) / sum((x - x_mean)^2)
        scores = [m.composite_score for m in self.history]
        x_mean = (n - 1) / 2.0
        y_mean = sum(scores) / n
        num = 0.0
        den = 0.0
        for i, y in enumerate(scores):
            dx = i - x_mean
            num += dx * (y - y_mean)
            den += dx * dx
        if den == 0.0:
            return 0.0
        return num / den

    def worst_dimension(self) -> str:
        """Identify the quality dimension dragging composite score down most."""
        if not self.history:
            return "none"
        window = self.history[-self.WINDOW_SIZE:]
        n = len(window)
        dim_means: Dict[str, float] = {
            "relevance": sum(m.relevance_score for m in window) / n,
            "coherence": sum(m.coherence_score for m in window) / n,
            "completeness": sum(m.completeness_score for m in window) / n,
            "satisfaction": sum(m.user_satisfaction for m in window) / n,
        }
        return min(dim_means, key=lambda k: dim_means[k])

    def summary(self) -> Dict[str, Any]:
        """Full quality tracker summary for diagnostics / logging."""
        return {
            "total_cycles": len(self.history),
            "window_size": self.WINDOW_SIZE,
            "baseline_locked": self._baseline_locked,
            "baseline_quality": round(self.baseline_quality(), 4),
            "current_quality": round(self.current_quality(), 4),
            "drift_detected": self.drift_detected(),
            "degradation_rate": round(self.degradation_rate(), 6),
            "worst_dimension": self.worst_dimension(),
        }

    # ── Internals ────────────────────────────────────────────────────────────

    @staticmethod
    def _mean_composite(window: List[EvaluationMetrics]) -> float:
        if not window:
            return 0.0
        return sum(m.composite_score for m in window) / len(window)

    def _fire_alert(self) -> None:
        detail = {
            "type": "quality_drift",
            "baseline": round(self._baseline_score, 4),
            "current": round(self.current_quality(), 4),
            "delta": round(self._baseline_score - self.current_quality(), 4),
            "degradation_rate": round(self.degradation_rate(), 6),
            "worst_dimension": self.worst_dimension(),
            "total_cycles": len(self.history),
        }
        logger.warning("QualityTracker: DRIFT ALERT — %s", detail)
        for cb in self.alert_callbacks:
            try:
                cb(detail)
            except Exception:
                logger.exception("QualityTracker: alert callback error")

    def __repr__(self) -> str:
        return (
            f"QualityTracker(cycles={len(self.history)}, "
            f"quality={self.current_quality():.3f}, "
            f"baseline={self.baseline_quality():.3f}, "
            f"drift={self.drift_detected()})"
        )


# ── CycleEvaluator ──────────────────────────────────────────────────────────

class CycleEvaluator:
    """Per-cycle evaluator — runs after every AI response.

    Produces an EvaluationMetrics for a single (query, response) pair
    by scoring relevance, coherence, completeness, and inferred user
    satisfaction from behavioural signals in the context dict.
    """

    def __init__(self) -> None:
        logger.debug("CycleEvaluator: initialised")

    # ── Public API ───────────────────────────────────────────────────────────

    def evaluate(
        self,
        query: str,
        response: str,
        context: Dict[str, Any],
        latency_ms: float,
        tokens: int,
    ) -> EvaluationMetrics:
        """Score a single AI response across all quality dimensions."""
        relevance = self._score_relevance(query, response)
        coherence = self._score_coherence(response)
        completeness = self._score_completeness(query, response)
        satisfaction = self._infer_satisfaction(context)

        metrics = EvaluationMetrics(
            cycle_id=context.get("cycle_id", 0),
            timestamp=time.time(),
            relevance_score=relevance,
            coherence_score=coherence,
            completeness_score=completeness,
            user_satisfaction=satisfaction,
            latency_ms=latency_ms,
            tokens_used=tokens,
            tool_calls=context.get("tool_calls", 0),
            errors=context.get("errors", 0),
        )
        logger.debug(
            "CycleEvaluator: cycle=%d composite=%.3f rel=%.3f coh=%.3f "
            "comp=%.3f sat=%.3f lat=%.1fms tok=%d",
            metrics.cycle_id, metrics.composite_score,
            relevance, coherence, completeness, satisfaction,
            latency_ms, tokens,
        )
        return metrics

    # ── Relevance ────────────────────────────────────────────────────────────

    def _score_relevance(self, query: str, response: str) -> float:
        """Token-overlap relevance (Jaccard + coverage blend).

        Short responses penalised; empty queries score 0.5 (neutral).
        """
        if len(response) < _MIN_RESPONSE_CHARS:
            return 0.1
        query_tokens = _word_set(query)
        resp_tokens = _word_set(response)
        if not query_tokens:
            return 0.5
        overlap = len(query_tokens & resp_tokens)
        union = len(query_tokens | resp_tokens)
        if union == 0:
            return 0.0
        coverage = overlap / len(query_tokens)
        jaccard = overlap / union
        return min(1.0, 0.6 * coverage + 0.4 * jaccard)

    # ── Coherence ────────────────────────────────────────────────────────────

    def _score_coherence(self, response: str) -> float:
        """Structural quality: length, sentence completeness, repetition."""
        n = len(response)
        if n < _MIN_RESPONSE_CHARS:
            return 0.0

        # Length score — sigmoid-like around 200-2000 chars
        if n < 20:
            length_score = 0.1
        elif n < 50 or n > _MAX_RESPONSE_CHARS:
            length_score = 0.4
        else:
            length_score = 1.0

        # Sentence completeness
        has_sentence = bool(re.search(r"[.!?]", response))
        sentence_score = 1.0 if has_sentence else 0.5

        # Repetition: 4-gram overlap ratio
        rep_score = 1.0 - _repetition_ratio(response, n_gram=4)

        return max(0.0, min(1.0, 0.35 * length_score + 0.35 * sentence_score + 0.30 * rep_score))

    # ── Completeness ─────────────────────────────────────────────────────────

    def _score_completeness(self, query: str, response: str) -> float:
        """Check that key content words from the query appear in the response."""
        resp_lower = response.lower()
        content_words = [
            w for w in _word_set(query) if w not in _STOPWORDS and len(w) > 3
        ]
        if not content_words:
            return 0.7  # nothing to check — default OK
        covered = sum(1 for w in content_words if w in resp_lower)
        return min(1.0, covered / len(content_words))

    # ── Satisfaction inference ────────────────────────────────────────────────

    def _infer_satisfaction(self, context: Dict[str, Any]) -> float:
        """Heuristic satisfaction from behavioural signals in the context.

        Signal map:
          follow_up_question  → 0.50  (ambiguous — user still engaged but unsatisfied)
          task_completion     → 0.90  (positive signal)
          correction_retry    → 0.20  (negative signal — user corrected the AI)
          explicit_positive   → 0.95  (user said "thanks", "perfect", etc.)
          explicit_negative   → 0.10  (user expressed frustration)
          no_signal           → 0.70  (assumed OK)
        """
        signal = context.get("satisfaction_signal", "no_signal")
        signal_map: Dict[str, float] = {
            "follow_up_question": 0.50,
            "task_completion": 0.90,
            "correction_retry": 0.20,
            "explicit_positive": 0.95,
            "explicit_negative": 0.10,
            "no_signal": 0.70,
        }
        score = signal_map.get(signal, 0.70)

        # Penalise if errors occurred
        errors = context.get("errors", 0)
        if errors > 0:
            penalty = min(0.3, errors * 0.10)
            score = max(0.0, score - penalty)

        return score


# ── Text utilities ───────────────────────────────────────────────────────────

def _word_set(text: str) -> Set[str]:
    """Extract lowercase word tokens (length >= 2)."""
    return set(re.findall(r"\b[a-z]{2,}\b", text.lower()))


def _repetition_ratio(text: str, n_gram: int = 4) -> float:
    """Fraction of repeated n-grams.  0.0 = no repetition, 1.0 = all repeated."""
    words = text.lower().split()
    if len(words) < n_gram * 2:
        return 0.0
    grams: List[str] = []
    for i in range(len(words) - n_gram + 1):
        grams.append(" ".join(words[i : i + n_gram]))
    if not grams:
        return 0.0
    unique = len(set(grams))
    return 1.0 - (unique / len(grams))
