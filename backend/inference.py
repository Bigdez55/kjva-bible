"""Compatibility facade binding the backend's legacy inference interface to the
CURRENT model path.

Serving inference is owned by the XMIND C engine. The old safetensors host bridge
(``KJVA.ai.xmind.kjva_byte_backend``) was removed in the 2026-06 KJVA migration; this
facade is the forward binding — it exposes the same names backend code imports
(``get_engine``, ``XmindKJVAInference``, the byte constants, the two exceptions),
backed by the live ``_xmind.XMindClient`` serving ``KJVA/training/gguf/canonical.gguf``.

No MLX, no training, no model policy here. Generation runs through the deployed,
parity-verified C engine (libxmind-core) exactly as the native ``api.py`` path does.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, Optional

# Byte-token semantics (PAD=0, BOS=1, EOS=2, byte b -> b+3). Kept for backend/test
# import compatibility; the C engine owns the actual tokenization.
PAD_ID = 0
BOS_ID = 1
EOS_ID = 2
BYTE_OFFSET = 3

# Architecture contract of the canonical KJVA model (byte-level LM). Matches
# training/gguf/canonical.gguf as loaded by the C engine.
EXPECTED_CONFIG = {
    "vocab_size": 259,
    "n_layers": 8,
    "d_model": 384,
    "n_heads": 6,
    "max_seq_len": 1024,
}

_REPO_ROOT = Path(__file__).resolve().parents[1]
# `_xmind` lives in the tokenless-agent src tree; make it importable regardless of
# how the backend was launched.
_AGENT_SRC = _REPO_ROOT / "KJVA" / "ai" / "tokenless-agent" / "src"
for _p in (_REPO_ROOT, _AGENT_SRC):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))


class XmindBackendError(RuntimeError):
    """Unrecoverable XMIND backend failure (engine unavailable or generation error)."""


class XmindPolicyHalt(XmindBackendError):
    """A pre/per-token/post generation hook halted output for policy reasons."""


def _load_client() -> Any:
    """Lazily bind the XMIND C engine client. The import is deferred to call time so
    module load never depends on sys.path ordering (the backend imports this module
    before kjva_runtime injects its own paths)."""
    from _xmind import get_client  # type: ignore  # noqa: E402

    return get_client()


class XmindKJVAInference:
    """Backend-facing engine with the legacy interface, backed by the live XMIND C
    engine (canonical.gguf). Generation flows through ``XMindClient.generate()``."""

    # Preserved verbatim: backend code and tests read this exact value.
    backend_name = "xmind-byte-host"

    def __init__(self, models_dir: Optional[Path] = None) -> None:
        self.models_dir = models_dir  # unused (the C engine resolves canonical.gguf)
        self._client: Any = None
        self._last_error = ""

    def _ensure_client(self) -> Any:
        if self._client is None:
            try:
                self._client = _load_client()
            except Exception as exc:  # noqa: BLE001
                self._last_error = f"_xmind client unavailable: {exc}"
                self._client = None
            if self._client is None and not self._last_error:
                self._last_error = (
                    "XMIND C engine did not initialize "
                    "(check canonical.gguf and libxmind-core build)."
                )
        return self._client

    @property
    def last_error(self) -> str:
        return self._last_error

    def is_ready(self) -> bool:
        client = self._ensure_client()
        if client is None:
            return False
        try:
            ready = bool(client.ready())
            self._last_error = "" if ready else "XMIND client bound but not ready."
            return ready
        except Exception as exc:  # noqa: BLE001
            self._last_error = str(exc)
            return False

    def status(self) -> Dict[str, Any]:
        client = self._ensure_client()
        ready = self.is_ready()
        version = ""
        info: Dict[str, Any] = {}
        if client is not None:
            try:
                version = client.version()
            except Exception:  # noqa: BLE001
                version = ""
            try:
                info = client.model_info()
            except Exception:  # noqa: BLE001
                info = {}
        return {
            "backend": self.backend_name,
            "ready": ready,
            "loaded": client is not None,
            "version": version,
            "model_info": info,
            "last_error": self._last_error,
            "byte_tokens": {
                "pad": PAD_ID,
                "bos": BOS_ID,
                "eos": EOS_ID,
                "byte_offset": BYTE_OFFSET,
            },
        }

    def complete(
        self,
        prompt: str,
        max_new_tokens: int = 150,
        temperature: float = 0.8,
        top_p: float = 0.9,
    ) -> str:
        """Generate a completion via the XMIND C engine. Raises ``XmindBackendError``
        if the engine is unavailable, ``XmindPolicyHalt`` on a hook halt."""
        client = self._ensure_client()
        if client is None:
            raise XmindBackendError(self._last_error or "XMIND C engine unavailable.")
        try:
            return client.generate(
                prompt,
                max_new=int(max_new_tokens),
                temperature=float(temperature),
                top_p=float(top_p),
            )
        except (XmindBackendError, XmindPolicyHalt):
            raise
        except Exception as exc:  # noqa: BLE001
            self._last_error = str(exc)
            raise XmindBackendError(str(exc)) from exc


KJVAInference = XmindKJVAInference

_engine: Optional[XmindKJVAInference] = None


def get_engine() -> XmindKJVAInference:
    global _engine
    if _engine is None:
        _engine = XmindKJVAInference()
    return _engine


__all__ = [
    "BYTE_OFFSET",
    "BOS_ID",
    "EOS_ID",
    "PAD_ID",
    "EXPECTED_CONFIG",
    "XmindBackendError",
    "XmindPolicyHalt",
    "KJVAInference",
    "XmindKJVAInference",
    "get_engine",
]
