"""
Per-member XMIND client. ctypes-based FFI to libxmind-core.{so,dylib}.

Identity-neutral by design:
  - No specific member names are hard-coded
  - Member name comes from env `MEMBER_NAME` or is passed explicitly
  - Persona file is loaded from `xmind_federation/personas/<MEMBER_NAME>.txt`
  - If no persona file exists, a generic placeholder is used + warning logged

Usage from a member daemon:

    from xmind_federation import XMindClient
    client = XMindClient(member_name=os.environ["MEMBER_NAME"])
    result = client.deliberate(
        domain="<domain label, e.g. economic, security, legal>",
        context="<short serialized context string>",
        question="<the question to reason about>",
    )
    print(result.decision, result.confidence)

Or as a thin helper from any caller:

    from xmind_federation import deliberate_as
    result = deliberate_as("<member_name>",
                           domain=..., context=..., question=...)
"""
from __future__ import annotations

import ctypes
import logging
import os
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger("xmind_federation")

# ──────────────────────────────────────────────────────────────────────
# Persona registry — each member supplies its own .txt file
# ──────────────────────────────────────────────────────────────────────
_PERSONA_DIR = Path(__file__).parent / "personas"


def _load_persona(member_name: str) -> str:
    """Load `personas/<member_name>.txt`. Falls back to a generic placeholder
    if the file is missing (with a warning), so the runtime works even before
    a consuming project has supplied its persona files."""
    p = _PERSONA_DIR / f"{member_name}.txt"
    if p.exists():
        return p.read_text(encoding="utf-8").strip()
    logger.warning(
        "[_xmind:%s] no persona file at %s — using generic placeholder. "
        "Create that file in your consuming project to define the member's role.",
        member_name, p,
    )
    return (
        f"You are {member_name}, a member of the deliberation federation. "
        "Reason carefully within your assigned domain and return a concise, "
        "decision-oriented response."
    )


# ──────────────────────────────────────────────────────────────────────
# Result type
# ──────────────────────────────────────────────────────────────────────
@dataclass
class DeliberationResult:
    member:     str
    decision:   str
    confidence: float
    reasoning:  str
    ai_powered: bool
    latency_ms: float

    def to_dict(self) -> dict:
        return {
            "member":     self.member,
            "decision":   self.decision,
            "confidence": self.confidence,
            "reasoning":  self.reasoning,
            "ai_powered": self.ai_powered,
            "latency_ms": self.latency_ms,
        }


# ──────────────────────────────────────────────────────────────────────
# ctypes FFI bindings to xmind_easy.c
# ──────────────────────────────────────────────────────────────────────
class _XMindFFI:
    """Loads libxmind-core and declares the xmind_easy_* ABI."""

    _lock = threading.Lock()
    _lib: Optional[ctypes.CDLL] = None

    @classmethod
    def load(cls, lib_path: Optional[str] = None) -> Optional[ctypes.CDLL]:
        with cls._lock:
            if cls._lib is not None:
                return cls._lib

            if lib_path is None:
                lib_path = os.environ.get("XMIND_LIB")
            if lib_path is None:
                # Auto-locate relative to repo / common install paths
                ext = "dylib" if sys.platform == "darwin" else "so"
                here = Path(__file__).resolve()
                # Try a few likely locations consuming projects use
                candidates = [
                    here.parents[1] / "ai" / "xmind" / "build" / f"libxmind-core.{ext}",
                    here.parents[2] / "ai" / "xmind" / "build" / f"libxmind-core.{ext}",
                    Path("/usr/local/lib") / f"libxmind-core.{ext}",
                ]
                for c in candidates:
                    if c.exists():
                        lib_path = str(c)
                        break

            if not lib_path or not Path(lib_path).exists():
                logger.warning("[_xmind] libxmind-core not found — stub mode")
                return None

            try:
                lib = ctypes.CDLL(lib_path)
            except OSError as exc:
                logger.warning("[_xmind] failed to load %s: %s", lib_path, exc)
                return None

            # Declare xmind_easy_* signatures
            lib.xmind_easy_init.argtypes  = [ctypes.c_char_p, ctypes.c_int]
            lib.xmind_easy_init.restype   = ctypes.c_int

            lib.xmind_easy_generate.argtypes = [
                ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int,
                ctypes.c_float, ctypes.c_float, ctypes.c_int,
            ]
            lib.xmind_easy_generate.restype = ctypes.c_int

            lib.xmind_easy_set_sampler.argtypes = [
                ctypes.c_float, ctypes.c_float, ctypes.c_ulonglong,
            ]
            lib.xmind_easy_set_sampler.restype = ctypes.c_int

            lib.xmind_easy_reset.argtypes = []
            lib.xmind_easy_reset.restype  = ctypes.c_int

            lib.xmind_easy_ready.argtypes = []
            lib.xmind_easy_ready.restype  = ctypes.c_int

            lib.xmind_easy_version.argtypes = []
            lib.xmind_easy_version.restype  = ctypes.c_char_p

            lib.xmind_easy_shutdown.argtypes = []
            lib.xmind_easy_shutdown.restype  = None

            # Optional: adapter load (LoRA via safetensors)
            try:
                lib.xmind_easy_load_adapter.argtypes = [ctypes.c_char_p]
                lib.xmind_easy_load_adapter.restype  = ctypes.c_int
                lib.xmind_easy_adapter_loaded.argtypes = []
                lib.xmind_easy_adapter_loaded.restype  = ctypes.c_int
            except AttributeError:
                pass  # older lib without adapter support

            cls._lib = lib
            logger.info("[_xmind] loaded %s — %s",
                        lib_path, lib.xmind_easy_version().decode())
            return lib


# ──────────────────────────────────────────────────────────────────────
# Per-member client
# ──────────────────────────────────────────────────────────────────────
class XMindClient:
    """One instance per federation member (per process).

    Each process resolves its member identity from (in order):
      1. constructor arg `member_name=...`
      2. environment variable `MEMBER_NAME`
      3. raises ValueError if neither is set

    Each daemon process owns its own libxmind-core + own session.
    """

    # Process-singleton init lock (xmind_easy_init is per-process)
    _init_lock = threading.Lock()
    _init_done = False
    _init_ok   = False

    def __init__(
        self,
        member_name: Optional[str] = None,
        *,
        model_path:  Optional[str] = None,
        lib_path:    Optional[str] = None,
        max_seq:     int   = 2048,
        temperature: float = 0.7,
        top_p:       float = 0.9,
    ) -> None:
        if member_name is None:
            member_name = os.environ.get("MEMBER_NAME")
        if not member_name:
            raise ValueError(
                "member_name is required — pass explicitly or set env MEMBER_NAME"
            )
        self.member_name = member_name
        self.persona     = _load_persona(member_name)
        self.temperature = float(temperature)
        self.top_p       = float(top_p)
        # Zero-config startup per UNIFIED_MASTER_TECH_PACK.md Part II §25.7
        # AND canonical-base doctrine (training/gguf/CANONICAL_BASE_DOCTRINE.md):
        # the single runtime base is `training/gguf/canonical.gguf`. Historical
        # checkpoints live in `training/gguf/archive/` and are NOT auto-loaded.
        # Override via XMIND_MODEL env var or `model_path=` kwarg only.
        _default_model = (
            Path(__file__).resolve().parent.parent
            / "training" / "gguf" / "canonical.gguf"
        )
        self.model_path = model_path or os.environ.get(
            "XMIND_MODEL", str(_default_model)
        )
        self._lib       = _XMindFFI.load(lib_path)
        self._stub_mode = False

        self._maybe_init(max_seq)

    def _maybe_init(self, max_seq: int) -> None:
        with XMindClient._init_lock:
            if XMindClient._init_done:
                self._stub_mode = not XMindClient._init_ok
                return

            if self._lib is None:
                self._stub_mode = True
                XMindClient._init_done = True
                XMindClient._init_ok   = False
                logger.warning(
                    "[_xmind:%s] no library available — stub responses",
                    self.member_name,
                )
                return

            if not os.path.exists(self.model_path):
                logger.warning(
                    "[_xmind:%s] model not found at %s — stub responses",
                    self.member_name, self.model_path,
                )
                self._stub_mode = True
                XMindClient._init_done = True
                XMindClient._init_ok   = False
                return

            t0 = time.time()
            rc = self._lib.xmind_easy_init(
                self.model_path.encode("utf-8"),
                int(max_seq),
            )
            dt = (time.time() - t0) * 1000
            if rc != 0:
                logger.error(
                    "[_xmind:%s] init failed rc=%d (model=%s)",
                    self.member_name, rc, self.model_path,
                )
                self._stub_mode = True
                XMindClient._init_ok = False
            else:
                logger.info(
                    "[_xmind:%s] init OK in %.1fms (model=%s)",
                    self.member_name, dt, self.model_path,
                )
                XMindClient._init_ok = True
                self._maybe_load_adapter()

            XMindClient._init_done = True

    def _maybe_load_adapter(self) -> None:
        """Locate + load this member's adapter (LoRA safetensors) if wired.

        Search order:
          1. env XMIND_ADAPTER (explicit override)
          2. <SOUL_DIR>/<member>/.adapter        (env SOUL_DIR or ./data/soul)
          3. ./data/soul/<member>/.adapter        (last resort default)
        """
        if self._lib is None or not hasattr(self._lib, "xmind_easy_load_adapter"):
            return

        candidates = []
        env_override = os.environ.get("XMIND_ADAPTER")
        if env_override:
            candidates.append(env_override)

        soul_dir = os.environ.get("SOUL_DIR_BASE",
                                   os.environ.get("SOUL_DIR", "./data/soul"))
        candidates.append(str(Path(soul_dir) / self.member_name / ".adapter"))
        candidates.append(f"./data/soul/{self.member_name}/.adapter")

        for c in candidates:
            p = Path(c).expanduser()
            if not p.exists():
                continue
            try:
                adapter_path = p.read_text(encoding="utf-8").strip()
            except Exception:
                continue
            if not adapter_path:
                continue
            ap = Path(adapter_path).expanduser()
            if not ap.exists():
                logger.warning(
                    "[_xmind:%s] .adapter points to missing file: %s",
                    self.member_name, ap,
                )
                continue
            rc = self._lib.xmind_easy_load_adapter(str(ap).encode("utf-8"))
            if rc == 0:
                logger.info("[_xmind:%s] adapter loaded: %s",
                            self.member_name, ap)
                return
            else:
                logger.warning(
                    "[_xmind:%s] adapter load rc=%d for %s",
                    self.member_name, rc, ap,
                )
                return
        # No adapter wired — base weights only (still federated via persona).

    # ── Public deliberation API ─────────────────────────────────────
    def deliberate(
        self,
        *,
        domain:    str,
        context:   str,
        question:  str,
        max_tokens: int = 256,
    ) -> DeliberationResult:
        """Run a single deliberation cycle. Returns a typed result.

        Composes persona + domain + context + question into a prompt,
        runs XMIND inference (or stub fallback), and returns the model's
        response with a confidence estimate.
        """
        prompt = self._compose_prompt(domain, context, question)
        t0 = time.time()

        if self._stub_mode or self._lib is None:
            text = self._stub_response(domain, context, question)
            ai_powered = False
        else:
            text = self._infer(prompt, max_tokens)
            ai_powered = bool(text)
            if not text:
                text = self._stub_response(domain, context, question)
                ai_powered = False

        latency_ms = (time.time() - t0) * 1000
        confidence = self._estimate_confidence(text, ai_powered)
        decision   = self._extract_decision(text)

        return DeliberationResult(
            member     = self.member_name,
            decision   = decision,
            confidence = confidence,
            reasoning  = text,
            ai_powered = ai_powered,
            latency_ms = latency_ms,
        )

    def reset(self) -> None:
        """Clear KV cache between independent prompts."""
        if not self._stub_mode and self._lib is not None:
            self._lib.xmind_easy_reset()

    # ── Internals ───────────────────────────────────────────────────
    def _compose_prompt(self, domain: str, context: str, question: str) -> str:
        return (
            f"{self.persona}\n\n"
            f"Domain: {domain}\n"
            f"Context: {context}\n\n"
            f"Question: {question}\n\n"
            f"Reply with a concise decision and brief reasoning (max 4 sentences):"
        )

    def _infer(self, prompt: str, max_tokens: int) -> str:
        buf_size = max(max_tokens * 8, 2048)
        out_buf  = ctypes.create_string_buffer(buf_size)
        n = self._lib.xmind_easy_generate(
            prompt.encode("utf-8"),
            out_buf,
            buf_size,
            ctypes.c_float(self.temperature),
            ctypes.c_float(self.top_p),
            int(max_tokens),
        )
        if n < 0:
            logger.warning("[_xmind:%s] generate rc=%d", self.member_name, n)
            return ""
        return out_buf.value.decode("utf-8", errors="replace").strip()

    def _stub_response(self, domain: str, context: str, question: str) -> str:
        """Deterministic placeholder so orchestration still works pre-training."""
        return (
            f"[stub:{self.member_name}] domain={domain!r} would deliberate on: "
            f"{question[:120]}. ai_powered=false (model not loaded). "
            "context-hash-marker: " + str(hash((domain, context, question)) & 0xFFFFFFFF)
        )

    @staticmethod
    def _estimate_confidence(text: str, ai_powered: bool) -> float:
        """Heuristic confidence: short, hedged responses → low; assertive → high."""
        if not text:
            return 0.0
        base = 0.65 if ai_powered else 0.35
        hedges = ("maybe", "perhaps", "might", "could be", "unsure", "uncertain")
        if any(h in text.lower() for h in hedges):
            base -= 0.15
        if len(text) > 400:
            base -= 0.05
        return max(0.0, min(1.0, base))

    @staticmethod
    def _extract_decision(text: str) -> str:
        """First sentence of the response is treated as the headline decision."""
        if not text:
            return "no-decision"
        for sep in (". ", "! ", "? ", "\n"):
            if sep in text:
                return text.split(sep, 1)[0].strip()
        return text[:200].strip()


# ──────────────────────────────────────────────────────────────────────
# Module-level convenience: deliberate_as("<member>", ...) one-liner
# Caches one client per member name in the current process.
# ──────────────────────────────────────────────────────────────────────
_member_clients: dict[str, XMindClient] = {}
_member_lock = threading.Lock()


def deliberate_as(
    member_name: str,
    *,
    domain:     str,
    context:    str,
    question:   str,
    max_tokens: int = 256,
) -> DeliberationResult:
    with _member_lock:
        client = _member_clients.get(member_name)
        if client is None:
            client = XMindClient(member_name=member_name)
            _member_clients[member_name] = client
    return client.deliberate(
        domain=domain, context=context, question=question, max_tokens=max_tokens,
    )
