"""
_xmind_glue.py — Generic XMIND wiring example.

This file shows the PATTERN for binding an agent handler to per-member XMIND
deliberation. It is intentionally generic — a consuming project copies this
shape per office or per handler and customizes the domain / context / question
strings to its own work.

Pattern:

  1. Lazily instantiate ONE XMindClient per process (the federated convention)
  2. Expose `deliberate_<action>()` helpers — each one a thin wrapper that
     composes a domain-specific prompt and returns a string the handler can use
  3. Fall back gracefully when no model is loaded yet (stub mode)

The helpers below are illustrative — `deliberate_classify` and
`deliberate_choose` are common patterns. Add or rename as the project needs.

Drop-in instructions:
  - Place per-office: copy this file to <office>/_xmind_glue.py
  - In the handler, `from ._xmind_glue import deliberate_classify` etc.
  - Set env `MEMBER_NAME` to the office's member name at daemon startup
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger("xmind_glue")

_client = None


def _get_client():
    """Shared XMindClient (the XMIND C engine). One model per process."""
    from _xmind import get_client
    return get_client()


def generate(prompt: str, *, max_new: int = 96, temperature: float = 0.0) -> Optional[str]:
    """Generate the model's continuation of ``prompt`` through the XMIND C engine — the
    sovereign inference path (ADR-0002 §3). Returns None ONLY when the engine genuinely
    cannot load (a real gap to close, surfaced by the caller — never a torch fallback)."""
    client = _get_client()
    if client is None:
        return None
    try:
        text = client.generate(prompt, max_new=max_new, temperature=temperature)
        return (text or "").strip() or None
    except Exception as exc:  # noqa: BLE001
        logger.error("[xmind_glue] XMIND generation failed: %s", exc)
        return None


# ──────────────────────────────────────────────────────────────────────
# Example helper 1 — classify an input into one of N categories
# ──────────────────────────────────────────────────────────────────────
def deliberate_classify(input_text: str, *, options: list[str],
                         context: str = "", domain: str = "classification") -> str:
    """Ask XMIND to pick one of `options` for `input_text`. Returns the chosen
    option string, or the first option as a safe default in stub mode."""
    client = _get_client()
    if not client:
        return options[0] if options else ""
    try:
        opts_csv = ", ".join(options)
        prompt = (f"{context}\nPick exactly ONE of [{opts_csv}] for: {input_text[:300]}\nChosen: ")
        text = (client.generate(prompt, max_new=32) or "").lower()
        for opt in options:
            if opt.lower() in text:
                return opt
        return options[0]  # safe default
    except Exception as exc:
        logger.debug("[xmind_glue] deliberate_classify failed: %s", exc)
        return options[0] if options else ""


# ──────────────────────────────────────────────────────────────────────
# Example helper 2 — open-ended deliberation, return reasoning text
# ──────────────────────────────────────────────────────────────────────
def deliberate_reason(question: str, *, context: str = "",
                       domain: str = "reasoning") -> str:
    """Ask XMIND to reason about `question`. Returns the reasoning text, or
    empty string in stub mode (caller should fall through to keyword logic)."""
    client = _get_client()
    if not client:
        return ""
    try:
        prompt = f"{context}\n{question}\n" if context else f"{question}\n"
        return client.generate(prompt, max_new=200) or ""
    except Exception as exc:  # noqa: BLE001
        logger.debug("[xmind_glue] deliberate_reason failed: %s", exc)
        return ""


# ──────────────────────────────────────────────────────────────────────
# Example helper 3 — yes/no/defer gate
# ──────────────────────────────────────────────────────────────────────
def deliberate_gate(proposition: str, *, context: str = "",
                     domain: str = "gate") -> str:
    """Ask XMIND to approve/reject/defer a proposition. Returns one of
    'approve' | 'reject' | 'defer'. Stub mode returns 'defer'."""
    client = _get_client()
    if not client:
        return "defer"
    try:
        res = client.deliberate(
            domain   = domain,
            context  = context,
            question = (
                f"Should this be approved? Reply with exactly one of: "
                f"approve, reject, defer. Proposition: {proposition[:300]}"
            ),
            max_tokens = 32,
        )
        t = res.reasoning.lower()
        for verdict in ("reject", "approve", "defer"):
            if verdict in t:
                return verdict
        return "defer"
    except Exception as exc:
        logger.debug("[xmind_glue] deliberate_gate failed: %s", exc)
        return "defer"
