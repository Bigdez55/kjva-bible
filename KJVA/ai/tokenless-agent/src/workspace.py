"""ai/tokenless-agent/src/workspace.py
WorkspaceManager — session lifecycle, conversation history, context windowing.

Backed by XSTORE ctypes FFI when available; falls back to an in-memory dict
so the module is always importable even without native binaries.
"""
from __future__ import annotations

import ctypes
import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("tokenless.workspace")

# ── Constants ─────────────────────────────────────────────────────────────────
SESSION_TIMEOUT: int = 1800          # seconds before idle session is reaped
MAX_HISTORY: int = 200               # max messages kept per session
_TOKEN_CHARS: int = 4                # chars-per-token heuristic (for windowing)

# ── XSTORE ctypes shim (optional) ────────────────────────────────────────────
_xstore: Optional[ctypes.CDLL] = None
_xstore_loaded: bool = False

def _try_load_xstore() -> None:
    global _xstore, _xstore_loaded
    if _xstore_loaded:
        return
    _xstore_loaded = True
    candidates = [
        "/usr/local/lib/libxstore.so",
        "/lib/libxstore.so",
        os.path.join(os.path.dirname(__file__), "../../../store/xstore/libxstore.so"),
    ]
    for path in candidates:
        try:
            lib = ctypes.CDLL(path)
            # Verify minimal symbols exist before trusting the library
            lib.xstore_open
            lib.xstore_put
            lib.xstore_get
            lib.xstore_close
            _xstore = lib
            logger.info("WorkspaceManager: XSTORE loaded from %s", path)
            return
        except (OSError, AttributeError):
            continue
    logger.debug("WorkspaceManager: XSTORE unavailable — using in-memory fallback")


# ── Data Types ────────────────────────────────────────────────────────────────

@dataclass
class WorkspaceState:
    """Complete state for a single AI session."""
    session_id: str
    created_at: float
    last_active: float
    conversation_history: List[Dict[str, Any]] = field(default_factory=list)
    open_files: List[str] = field(default_factory=list)
    active_context: Dict[str, Any] = field(default_factory=dict)
    pending_actions: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "created_at": self.created_at,
            "last_active": self.last_active,
            "conversation_history": self.conversation_history,
            "open_files": self.open_files,
            "active_context": self.active_context,
            "pending_actions": self.pending_actions,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "WorkspaceState":
        return cls(
            session_id=d["session_id"],
            created_at=d["created_at"],
            last_active=d["last_active"],
            conversation_history=d.get("conversation_history", []),
            open_files=d.get("open_files", []),
            active_context=d.get("active_context", {}),
            pending_actions=d.get("pending_actions", []),
        )


# ── WorkspaceManager ──────────────────────────────────────────────────────────

class WorkspaceManager:
    """
    Manages the lifecycle of AI workspace sessions.

    Thread-safety: single-threaded Sprint scope — no locking added.
    Persistence: attempts XSTORE ctypes FFI; falls back to in-memory dict.
    """

    def __init__(self) -> None:
        _try_load_xstore()
        self._sessions: Dict[str, WorkspaceState] = {}
        self._xstore_ctx: Optional[ctypes.c_void_p] = None
        self._init_xstore_ctx()

    # ── XSTORE context ────────────────────────────────────────────────────────

    def _init_xstore_ctx(self) -> None:
        if _xstore is None:
            return
        try:
            _xstore.xstore_open.restype = ctypes.c_void_p
            _xstore.xstore_open.argtypes = [ctypes.c_char_p, ctypes.c_int]
            ctx = _xstore.xstore_open(b"tokenless_workspace", 0)
            if ctx:
                self._xstore_ctx = ctypes.c_void_p(ctx)
        except Exception as exc:  # noqa: BLE001
            logger.warning("WorkspaceManager: xstore_open failed: %s", exc)

    def _xstore_put(self, key: str, value: str) -> bool:
        if _xstore is None or self._xstore_ctx is None:
            return False
        try:
            _xstore.xstore_put.restype = ctypes.c_int
            _xstore.xstore_put.argtypes = [
                ctypes.c_void_p, ctypes.c_char_p, ctypes.c_size_t,
                ctypes.c_char_p, ctypes.c_size_t,
            ]
            kb = key.encode()
            vb = value.encode()
            rc = _xstore.xstore_put(
                self._xstore_ctx, kb, len(kb), vb, len(vb)
            )
            return rc == 0
        except Exception as exc:  # noqa: BLE001
            logger.debug("xstore_put failed: %s", exc)
            return False

    def _xstore_get(self, key: str) -> Optional[str]:
        if _xstore is None or self._xstore_ctx is None:
            return None
        try:
            buf = ctypes.create_string_buffer(65536)
            buf_len = ctypes.c_size_t(len(buf))
            _xstore.xstore_get.restype = ctypes.c_int
            _xstore.xstore_get.argtypes = [
                ctypes.c_void_p, ctypes.c_char_p, ctypes.c_size_t,
                ctypes.c_char_p, ctypes.POINTER(ctypes.c_size_t),
            ]
            kb = key.encode()
            rc = _xstore.xstore_get(
                self._xstore_ctx, kb, len(kb), buf, ctypes.byref(buf_len)
            )
            if rc == 0:
                return buf.raw[: buf_len.value].decode(errors="replace")
        except Exception as exc:  # noqa: BLE001
            logger.debug("xstore_get failed: %s", exc)
        return None

    # ── Lazy reaper ───────────────────────────────────────────────────────────

    def _reap_expired(self) -> None:
        now = time.monotonic()
        expired = [
            sid for sid, ws in self._sessions.items()
            if now - ws.last_active > SESSION_TIMEOUT
        ]
        for sid in expired:
            logger.info("WorkspaceManager: reaping expired session %s", sid)
            del self._sessions[sid]

    # ── Public API ────────────────────────────────────────────────────────────

    def create_session(self, session_id: Optional[str] = None) -> WorkspaceState:
        """Create a new workspace session and return it."""
        self._reap_expired()
        sid = session_id or str(uuid.uuid4())
        now = time.monotonic()
        ws = WorkspaceState(session_id=sid, created_at=now, last_active=now)
        self._sessions[sid] = ws
        self.persist(ws)
        logger.debug("WorkspaceManager: created session %s", sid)
        return ws

    def get_session(self, session_id: str) -> Optional[WorkspaceState]:
        """Return session by ID, updating last_active. Returns None if not found/expired."""
        self._reap_expired()
        ws = self._sessions.get(session_id)
        if ws is None:
            # Try loading from XSTORE
            ws = self.load(session_id)
            if ws is None:
                return None
            self._sessions[session_id] = ws
        now = time.monotonic()
        if now - ws.last_active > SESSION_TIMEOUT:
            del self._sessions[session_id]
            return None
        ws.last_active = now
        return ws

    def update_session(self, ws: WorkspaceState) -> None:
        """Persist updated workspace state."""
        ws.last_active = time.monotonic()
        self._sessions[ws.session_id] = ws
        self.persist(ws)

    def close_session(self, session_id: str) -> bool:
        """Remove session from memory and XSTORE. Returns True if session existed."""
        ws = self._sessions.pop(session_id, None)
        if ws is None:
            return False
        logger.debug("WorkspaceManager: closed session %s", session_id)
        return True

    # ── Message helpers ───────────────────────────────────────────────────────

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Append a message to conversation history. Trims to MAX_HISTORY."""
        ws = self.get_session(session_id)
        if ws is None:
            return False
        entry: Dict[str, Any] = {
            "role": role,
            "content": content,
            "ts": time.monotonic(),
        }
        if metadata:
            entry["meta"] = metadata
        ws.conversation_history.append(entry)
        if len(ws.conversation_history) > MAX_HISTORY:
            # Drop oldest 20% to avoid constant single-element trimming
            trim = MAX_HISTORY // 5
            ws.conversation_history = ws.conversation_history[trim:]
        self.update_session(ws)
        return True

    def get_context_window(
        self, session_id: str, max_tokens: int = 2048
    ) -> List[Dict[str, Any]]:
        """
        Return the most-recent messages that fit within max_tokens.
        Uses a 1-token-per-4-chars heuristic.
        Messages are returned in chronological order.
        """
        ws = self.get_session(session_id)
        if ws is None:
            return []
        window: List[Dict[str, Any]] = []
        budget = max_tokens
        for msg in reversed(ws.conversation_history):
            chars = len(msg.get("content", ""))
            tokens = max(1, chars // _TOKEN_CHARS)
            if tokens > budget:
                break
            budget -= tokens
            window.append(msg)
        window.reverse()
        return window

    # ── Persistence ───────────────────────────────────────────────────────────

    def persist(self, ws: WorkspaceState) -> None:
        """Write workspace state to XSTORE (no-op on fallback)."""
        key = f"ws:{ws.session_id}"
        try:
            payload = json.dumps(ws.to_dict())
            self._xstore_put(key, payload)
        except Exception as exc:  # noqa: BLE001
            logger.debug("WorkspaceManager.persist failed: %s", exc)

    def load(self, session_id: str) -> Optional[WorkspaceState]:
        """Load workspace state from XSTORE. Returns None on miss or fallback."""
        key = f"ws:{session_id}"
        raw = self._xstore_get(key)
        if raw is None:
            return None
        try:
            d = json.loads(raw)
            return WorkspaceState.from_dict(d)
        except (json.JSONDecodeError, KeyError) as exc:
            logger.warning("WorkspaceManager.load: corrupt state for %s: %s", session_id, exc)
            return None

    # ── Diagnostics ───────────────────────────────────────────────────────────

    def active_session_count(self) -> int:
        return len(self._sessions)

    def session_ids(self) -> List[str]:
        return list(self._sessions.keys())
