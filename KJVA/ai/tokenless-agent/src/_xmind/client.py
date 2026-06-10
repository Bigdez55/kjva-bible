"""_xmind/client.py — XMindClient: the Python binding to the XMIND C inference engine.

This is the SOVEREIGN inference path (ADR-0002 §3 "Inference Engine" = ai/xmind). Generation
runs through the deployed, parity-verified XMIND C engine (libxmind-core) via the flat
ctypes-friendly `xmind_easy_*` API — NOT through any Python/torch shortcut. One model per
process (the C side is a singleton): use `get_client()` for the shared instance.

The engine also applies OMNI-PEFT adapters at inference (`xmind_easy_load_adapter`) — the
absorption path: load an adapter on top of the base, and `generate()` applies its delta.
"""
from __future__ import annotations

import ctypes
import logging
import os
import sys
from pathlib import Path
from typing import Optional

logger = logging.getLogger("tokenless.xmind.client")

_THIS = Path(__file__).resolve()
_V7 = _THIS.parents[4]                      # _xmind -> src -> tokenless-agent -> ai -> models v7


def _find_lib() -> Optional[str]:
    name = "libxmind-core.dylib" if sys.platform == "darwin" else "libxmind-core.so"
    candidates = [
        os.environ.get("XMIND_LIB", ""),
        str(_V7 / "ai" / "xmind" / "build" / name),
    ]
    for c in candidates:
        if c and os.path.exists(c):
            return c
    return None


def _find_weights() -> Optional[str]:
    for c in (os.environ.get("TOKENLESS_WEIGHTS", ""),
              os.environ.get("XMIND_MODEL_PATH", ""),
              str(_V7 / "training" / "gguf" / "canonical.gguf"),
              str(_V7 / "training" / "gguf" / "clean_base_soup_v1.gguf"),
              str(_V7 / "training" / "gguf" / "clean_base_v1.gguf")):
        if c and os.path.exists(c):
            return c
    return None


def _find_adapter() -> Optional[str]:
    """An OMNI-PEFT adapter to absorb on top of the base — OPT-IN only.

    There is deliberately NO default: the base XMIND model is the default
    behaviour, and loading an adapter silently would change generation without
    the operator's knowledge. Absorption is an explicit act — set TOKENLESS_ADAPTER
    (or XMIND_ADAPTER) to a safetensors adapter path to engage it.
    """
    for c in (os.environ.get("TOKENLESS_ADAPTER", ""),
              os.environ.get("XMIND_ADAPTER", "")):
        if c and os.path.exists(c):
            return c
    return None


class XMindUnavailable(RuntimeError):
    """Raised when the XMIND C engine or its weights cannot be loaded. There is NO fallback —
    this surfaces a real gap to close (build ai/xmind, provide weights), not a workaround."""


class XMindClient:
    """Per-process binding to the XMIND C engine. Construct once (via get_client())."""

    def __init__(self, model_path: Optional[str] = None, max_seq_len: int = 1024) -> None:
        lib_path = _find_lib()
        if lib_path is None:
            raise XMindUnavailable("libxmind-core not built — run `make` in ai/xmind")
        weights = model_path or _find_weights()
        if weights is None:
            raise XMindUnavailable("no XMIND weights (.gguf) found in training/gguf")
        self._lib = ctypes.CDLL(lib_path)
        self._bind()
        rc = self._lib.xmind_easy_init(weights.encode("utf-8"), int(max_seq_len))
        if rc != 0:
            raise XMindUnavailable(f"xmind_easy_init failed (rc={rc}) on {weights}")
        self.model_path = weights
        self.adapter_path: Optional[str] = None
        logger.info("XMindClient ready — engine=%s model=%s",
                    self.version(), os.path.basename(weights))
        # Absorption path (ADR-0002 §9): if an adapter is configured, load it on top
        # of the base so generate() applies its delta. Opt-in — the consumer is now
        # genuinely CALLED in the runtime (not just by tests), but only when an
        # operator deliberately engages it. A configured-but-refused adapter is a real
        # gap surfaced loudly, never a silent skip.
        adapter = _find_adapter()
        if adapter:
            if self.load_adapter(adapter):
                self.adapter_path = adapter
                logger.info("XMindClient absorbed adapter — %s (delta active)",
                            os.path.basename(adapter))
            else:
                logger.error("XMindClient adapter REFUSED/failed — %s (base only; close this gap)",
                             adapter)

    def _bind(self) -> None:
        lib = self._lib
        lib.xmind_easy_init.argtypes = [ctypes.c_char_p, ctypes.c_int]
        lib.xmind_easy_init.restype = ctypes.c_int
        lib.xmind_easy_generate.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int,
                                            ctypes.c_float, ctypes.c_float, ctypes.c_int]
        lib.xmind_easy_generate.restype = ctypes.c_int
        lib.xmind_easy_load_adapter.argtypes = [ctypes.c_char_p]
        lib.xmind_easy_load_adapter.restype = ctypes.c_int
        lib.xmind_easy_adapter_loaded.restype = ctypes.c_int
        lib.xmind_easy_set_sampler.argtypes = [ctypes.c_float, ctypes.c_float, ctypes.c_ulonglong]
        lib.xmind_easy_set_sampler.restype = ctypes.c_int
        lib.xmind_easy_reset.restype = ctypes.c_int
        lib.xmind_easy_ready.restype = ctypes.c_int
        lib.xmind_easy_version.restype = ctypes.c_char_p
        lib.xmind_easy_model_info.argtypes = [ctypes.c_char_p, ctypes.c_int]
        lib.xmind_easy_model_info.restype = ctypes.c_int
        lib.xmind_easy_adapter_ir.argtypes = [ctypes.c_char_p, ctypes.c_int]
        lib.xmind_easy_adapter_ir.restype = ctypes.c_int
        lib.xmind_easy_shutdown.restype = None

    def ready(self) -> bool:
        return bool(self._lib.xmind_easy_ready())

    def version(self) -> str:
        v = self._lib.xmind_easy_version()
        return v.decode("utf-8", "replace") if v else "unknown"

    def load_adapter(self, adapter_path: str) -> bool:
        """Load an OMNI-PEFT adapter on top of the base; its delta applies at inference."""
        return self._lib.xmind_easy_load_adapter(adapter_path.encode("utf-8")) == 0

    def adapter_loaded(self) -> bool:
        return bool(self._lib.xmind_easy_adapter_loaded())

    def model_info(self) -> dict:
        """Materialized-model facts (ADR-0002 §8.2 model-artifact materialization) as a dict,
        read from the C engine. Empty dict if unavailable."""
        import json
        buf = ctypes.create_string_buffer(512)
        n = self._lib.xmind_easy_model_info(buf, len(buf))
        if n <= 0:
            return {}
        try:
            return json.loads(buf.value.decode("utf-8", "replace"))
        except Exception:  # noqa: BLE001
            return {}

    def adapter_ir(self) -> dict:
        """Loaded adapter's IR descriptor (§11.1) as a dict, read from the C engine. Empty if
        no adapter is loaded."""
        import json
        buf = ctypes.create_string_buffer(256)
        n = self._lib.xmind_easy_adapter_ir(buf, len(buf))
        if n <= 0:
            return {}
        try:
            return json.loads(buf.value.decode("utf-8", "replace"))
        except Exception:  # noqa: BLE001
            return {}

    def generate(self, prompt: str, *, max_new: int = 96, temperature: float = 0.0,
                 top_p: float = 1.0) -> str:
        """Generate the model's continuation of ``prompt`` via the XMIND C engine."""
        self._lib.xmind_easy_reset()                 # independent prompt -> clear KV
        out = ctypes.create_string_buffer(max(1024, max_new * 8))
        n = self._lib.xmind_easy_generate(prompt.encode("utf-8"), out, len(out),
                                          ctypes.c_float(temperature), ctypes.c_float(top_p),
                                          int(max_new))
        if n < 0:
            raise XMindUnavailable(f"xmind_easy_generate failed (rc={n})")
        return out.value.decode("utf-8", "replace")


_client: Optional[XMindClient] = None
_init_failed = False


def get_client() -> Optional[XMindClient]:
    """Shared per-process XMindClient. Returns None only if the engine genuinely cannot load
    (a real gap to fix — never a silent torch fallback)."""
    global _client, _init_failed
    if _client is not None:
        return _client
    if _init_failed:
        return None
    try:
        _client = XMindClient()
        return _client
    except Exception as exc:  # noqa: BLE001
        _init_failed = True
        logger.error("XMIND engine unavailable (NO fallback — close this gap): %s", exc)
        return None
