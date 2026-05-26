"""soul_manager.py
SoulManager — agent memory namespace manager.

Implements 4 bucket types: persistent, episodic, context, meta.
Key schema: soul:{agent}:{bucket}:{sub-path}

Primary backend: XSTORE B-tree via ctypes FFI (libxstore.so).
File-backed fallback: JSONL append-only journal (M19) for persistence
when XSTORE is unavailable.  On startup, existing JSONL entries are
replayed into the in-memory dict so state survives restarts.

Security model (Sprint 45 P1 hardening):
  AES-256-GCM is MANDATORY for soul data persistence.  This module
  delegates all encryption to aes_gcm_bridge.py, which provides:
    Tier 1: xsec native library (libxsec.so) — production path.
    Tier 2: Python 'cryptography' package — real AES-GCM, acceptable in CI.
  If neither tier is available, aes_gcm_bridge raises AesGcmUnavailable.
  SoulManager propagates that exception as SoulManagerCryptoError —
  soul data is NEVER stored without verified AES-256-GCM encryption.

  The ONLY escape hatch is TOKENLESS_SOUL_ALLOW_PLAINTEXT=1, which enables
  a SHA-256 XOR dev fallback for local development only.  This env var
  MUST NOT be set in any production or CI environment.  It emits ERROR
  logs on every use and records a plaintext_warning marker in data.

Thread-safe via asyncio.Lock.
"""
from __future__ import annotations

import asyncio
import base64
import ctypes
import hashlib
import json
import logging
import os
import secrets
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Valid bucket names
VALID_BUCKETS = frozenset({"persistent", "episodic", "context", "meta"})


class SoulManagerError(Exception):
    pass


class SoulManagerCryptoError(SoulManagerError):
    """Raised when AES-GCM encryption is unavailable and plaintext fallback
    is disabled.  Soul data MUST NOT be persisted without verified encryption.
    """


# ── AES-GCM backend via aes_gcm_bridge ───────────────────────────────────
#
# aes_gcm_bridge.py implements a strict two-tier strategy with no plaintext
# downgrade.  Import it here; any failure to initialise a valid cipher backend
# is surfaced at call-time as AesGcmUnavailable.
#
# We import lazily inside the encrypt/decrypt helpers so that import errors
# are captured and converted to SoulManagerCryptoError rather than crashing
# module load for unrelated callers.

try:
    from .aes_gcm_bridge import (
        AesGcmUnavailable,
    )
    from .aes_gcm_bridge import (
        aes_gcm_decrypt as _bridge_decrypt,
    )
    from .aes_gcm_bridge import (  # type: ignore[import]
        aes_gcm_encrypt as _bridge_encrypt,
    )
    from .aes_gcm_bridge import (
        backend_name as _bridge_backend_name,
    )
    _BRIDGE_AVAILABLE = True
    logger.info(
        "SoulManager: local aes_gcm_bridge loaded (backend: %s)",
        _bridge_backend_name(),
    )
except ImportError as _imp_err:
    _BRIDGE_AVAILABLE = False
    _bridge_encrypt = None  # type: ignore[assignment]
    _bridge_decrypt = None  # type: ignore[assignment]
    _bridge_backend_name = None  # type: ignore[assignment]

    class AesGcmUnavailable(RuntimeError):  # type: ignore[no-redef]
        """Fallback sentinel when aes_gcm_bridge itself cannot be imported."""

    logger.error(
        "SoulManager: local aes_gcm_bridge not importable: %s. "
        "Soul data cannot be encrypted. Set TOKENLESS_SOUL_ALLOW_PLAINTEXT=1 "
        "for development ONLY.",
        _imp_err,
    )

# ── Dev-only plaintext escape hatch ──────────────────────────────────────
#
# TOKENLESS_SOUL_ALLOW_PLAINTEXT=1 permits the SHA-256 XOR fallback used in
# unit-test environments where libxsec.so and the 'cryptography' package
# are both absent.  NEVER set this in production or CI.

_ALLOW_PLAINTEXT = os.environ.get("TOKENLESS_SOUL_ALLOW_PLAINTEXT", "0").strip() == "1"
if _ALLOW_PLAINTEXT:
    logger.error(
        "SECURITY: TOKENLESS_SOUL_ALLOW_PLAINTEXT=1 is set. "
        "Soul data will be stored with SHA-256 XOR — NOT AES-256-GCM. "
        "This is INSECURE and MUST NOT be used in production or CI."
    )


def _crypto_available() -> bool:
    """Return True if a valid AES-GCM backend is wired up."""
    return bool(_BRIDGE_AVAILABLE and _bridge_encrypt is not None)


def _derive_key(agent: str, master_secret: bytes) -> bytes:
    """Derive a per-agent AES-256 key from master secret + agent name.

    Uses HKDF-SHA256 pattern (simplified).
    In production, use the XSEC HKDF implementation via ctypes FFI.
    """
    return hashlib.sha256(master_secret + agent.encode("utf-8")).digest()


def _encrypt_value(plaintext: bytes, key: bytes) -> bytes:
    """Encrypt a value using AES-256-GCM (via aes_gcm_bridge).

    Format: nonce(12) || ciphertext || tag(16)

    Fail-closed: raises SoulManagerCryptoError if no authenticated cipher
    backend is available and TOKENLESS_SOUL_ALLOW_PLAINTEXT is not set.
    """
    if _crypto_available():
        nonce = secrets.token_bytes(12)
        try:
            ct, tag = _bridge_encrypt(key, nonce, plaintext)
        except AesGcmUnavailable as exc:
            raise SoulManagerCryptoError(
                "Cannot persist soul state: AES-GCM backend became unavailable. "
                f"Detail: {exc}"
            ) from exc
        return nonce + ct + tag

    # Bridge unavailable — fail-closed unless dev escape hatch is active.
    if not _ALLOW_PLAINTEXT:
        raise SoulManagerCryptoError(
            "Cannot persist soul state without verified AES-256-GCM. "
            "aes_gcm_bridge is not available and TOKENLESS_SOUL_ALLOW_PLAINTEXT is not set. "
            "Install 'cryptography' package or provide libxsec.so via XSEC_LIB_PATH."
        )

    # ------------------------------------------------------------------ #
    # DEV-ONLY PLAINTEXT FALLBACK — SHA-256 CTR stream cipher.            #
    # NOT authenticated encryption. NOT suitable for any non-dev use.     #
    # ------------------------------------------------------------------ #
    logger.error(
        "SECURITY FALLBACK ACTIVE (TOKENLESS_SOUL_ALLOW_PLAINTEXT=1): "
        "Soul data is NOT protected by AES-256-GCM. "
        "This path is INSECURE and MUST NOT be used outside of development."
    )
    nonce = secrets.token_bytes(12)
    stream = b""
    ctr = 0
    while len(stream) < len(plaintext) + 16:
        block = hashlib.sha256(key + nonce + ctr.to_bytes(4, "big")).digest()
        stream += block
        ctr += 1
    ct = bytes(p ^ s for p, s in zip(plaintext, stream[: len(plaintext)], strict=False))
    # INSECURE: truncated SHA-256 is not an AEAD tag.
    tag = hashlib.sha256(key + nonce + ct).digest()[:16]
    return nonce + ct + tag


def _decrypt_value(encrypted: bytes, key: bytes) -> bytes | None:
    """Decrypt a value. Returns None if tag verification / decryption fails.

    Uses aes_gcm_bridge for authenticated decryption.  Falls back to the
    SHA-256 CTR path only when TOKENLESS_SOUL_ALLOW_PLAINTEXT=1 (dev only).

    Returns None on any authentication or format failure — never raises.
    """
    if len(encrypted) < 28:  # 12 nonce + 0 ct + 16 tag minimum
        return None
    nonce = encrypted[:12]
    tag = encrypted[-16:]
    ct = encrypted[12:-16]

    if _crypto_available():
        try:
            return _bridge_decrypt(key, nonce, ct, tag)
        except (AesGcmUnavailable, RuntimeError):
            return None  # Tag mismatch or backend failure

    # Dev plaintext fallback
    if not _ALLOW_PLAINTEXT:
        # No bridge and no escape hatch — cannot decrypt.
        logger.error(
            "SoulManager: _decrypt_value called with no AES-GCM backend and "
            "TOKENLESS_SOUL_ALLOW_PLAINTEXT not set — returning None."
        )
        return None

    logger.error(
        "SECURITY FALLBACK ACTIVE (TOKENLESS_SOUL_ALLOW_PLAINTEXT=1): "
        "Soul data tag verification is NOT performed by AES-256-GCM."
    )
    expected_tag = hashlib.sha256(key + nonce + ct).digest()[:16]
    if not secrets.compare_digest(tag, expected_tag):
        return None
    stream = b""
    ctr = 0
    while len(stream) < len(ct):
        block = hashlib.sha256(key + nonce + ctr.to_bytes(4, "big")).digest()
        stream += block
        ctr += 1
    return bytes(c ^ s for c, s in zip(ct, stream[: len(ct)], strict=False))


# Master encryption secret — in production, loaded from Secure Boot chain
# or platform secret storage.  Set TOKENLESS_SOUL_MASTER_SECRET_HEX to a 64-char hex
# string (32 bytes) to inject the production secret.  For development only,
# a fixed seed is used as the final fallback.
#
# TOKENLESS_STRICT_CRYPTO=1: refuses the dev seed and raises SoulManagerCryptoError
# at module load time if no production secret is injected.  Set this flag on
# all production and CI images to prevent accidental use of the dev seed.

_DEV_SEED: bytes = hashlib.sha256(b"TOKENLESS_SOUL_MASTER_KEY_DEV_2026").digest()

_master_secret_hex = os.environ.get("TOKENLESS_SOUL_MASTER_SECRET_HEX", "").strip()
if _master_secret_hex:
    try:
        _injected = bytes.fromhex(_master_secret_hex)
        if len(_injected) != 32:
            raise SoulManagerCryptoError(
                "TOKENLESS_SOUL_MASTER_SECRET_HEX must decode to exactly 32 bytes "
                f"(got {len(_injected)})."
            )
        _MASTER_SECRET: bytes = _injected
        logger.info("SoulManager: production master secret loaded from env.")
    except ValueError as _hex_err:
        raise SoulManagerCryptoError(
            f"TOKENLESS_SOUL_MASTER_SECRET_HEX is not valid hex: {_hex_err}"
        ) from _hex_err
else:
    # No production secret injected — use dev seed.
    _MASTER_SECRET = _DEV_SEED
    _strict_crypto = os.environ.get("TOKENLESS_STRICT_CRYPTO", "0").strip() == "1"
    if _strict_crypto:
        raise SoulManagerCryptoError(
            "TOKENLESS_STRICT_CRYPTO=1: production master secret is required but "
            "TOKENLESS_SOUL_MASTER_SECRET_HEX is not set.  "
            "Soul data MUST NOT be persisted with the development seed in "
            "production environments."
        )
    logger.warning(
        "SoulManager: using dev seed for _MASTER_SECRET. "
        "Set TOKENLESS_SOUL_MASTER_SECRET_HEX for production use."
    )


# ── M19: XSTORE B-tree backend for soul data persistence ──────────────────
#
# XStoreBackend wraps the XSTORE C library (libxstore.so) via ctypes.
# The C API used (from store/xstore/ffi/python_ffi.c):
#   xstore_ffi.open(path) → int          (0 = ok)
#   xstore_ffi.set(key, value) → int      (0 = ok)
#   xstore_ffi.get(key) → bytes | None
#   xstore_ffi.delete(key) → int          (0 = ok, -3 = not found)
#
# When the native library is unavailable, XStoreBackend.available is False
# and SoulManager falls back to the in-memory dict backend.

class XStoreBackend:
    """XSTORE B-tree backend for soul data persistence.

    Loads libxstore.so (or the Python extension module xstore_ffi) and
    provides get/put/delete/list_keys operations over the XSTORE B-tree.
    All keys and values are bytes objects.
    """

    def __init__(self) -> None:
        self._lib = None
        self._ffi_module = None
        self.available = False
        self._store_path = os.environ.get(
            "XSTORE_DB_PATH", "/var/lib/tokenless/soul.xstore"
        )
        self._init_backend()

    def _init_backend(self) -> None:
        """Try to load XSTORE — first as Python extension, then as ctypes."""
        # Strategy 1: Try importing the compiled Python extension module
        try:
            import importlib
            self._ffi_module = importlib.import_module("xstore_ffi")
            rc = self._ffi_module.open(self._store_path.encode("utf-8"))
            if rc == 0:
                self.available = True
                logger.info(
                    "XSTORE backend available via xstore_ffi module at %s",
                    self._store_path,
                )
                return
            logger.warning("xstore_ffi.open() returned %d", rc)
        except (ImportError, AttributeError, OSError) as e:
            logger.debug("xstore_ffi module not available: %s", e)

        # Strategy 2: Try loading libxstore.so via ctypes
        lib_path = os.environ.get(
            "XSTORE_LIB_PATH", "/usr/lib/tokenless/libxstore.so"
        )
        search_paths = [lib_path]
        _project_root = Path(__file__).resolve().parents[3]
        for suffix in ("libxstore.so", "libxstore.dylib"):
            search_paths.append(str(_project_root / "build" / "xstore" / suffix))
            search_paths.append(str(_project_root / "store" / "xstore" / suffix))

        for path in search_paths:
            try:
                self._lib = ctypes.CDLL(path)
                self.available = True
                logger.info("XSTORE backend available via ctypes at %s", path)
                return
            except OSError:
                continue

        logger.warning(
            "XSTORE library not available — using in-memory fallback. "
            "Set XSTORE_LIB_PATH or XSTORE_DB_PATH for production use."
        )

    def get(self, key: str) -> Optional[bytes]:
        """Retrieve a value by key from XSTORE. Returns None if not found."""
        if not self.available:
            return None
        key_bytes = key.encode("utf-8")
        try:
            if self._ffi_module is not None:
                result = self._ffi_module.get(key_bytes)
                return result  # bytes or None
            if self._lib is not None:
                # ctypes path: call xstore_get via the C FFI
                # This path requires the library to expose a simple get API
                buf = ctypes.create_string_buffer(65536)  # XSTORE_MAX_VAL_LEN
                buf_len = ctypes.c_uint32(65536)
                out_len = ctypes.c_uint32(0)
                rc = self._lib.xstore_ffi_get(
                    key_bytes, len(key_bytes),
                    buf, buf_len, ctypes.byref(out_len),
                )
                if rc == 0:
                    return buf.raw[: out_len.value]
                return None  # Not found or error
        except Exception as e:
            logger.warning("XSTORE get failed for key %s: %s", key, e)
        return None

    def put(self, key: str, value: bytes) -> bool:
        """Store a key-value pair in XSTORE. Returns True on success."""
        if not self.available:
            return False
        key_bytes = key.encode("utf-8")
        try:
            if self._ffi_module is not None:
                rc = self._ffi_module.set(key_bytes, value)
                return rc == 0
            if self._lib is not None:
                rc = self._lib.xstore_ffi_set(
                    key_bytes, len(key_bytes), value, len(value),
                )
                return rc == 0
        except Exception as e:
            logger.warning("XSTORE put failed for key %s: %s", key, e)
        return False

    def delete(self, key: str) -> bool:
        """Delete a key from XSTORE. Returns True if it existed."""
        if not self.available:
            return False
        key_bytes = key.encode("utf-8")
        try:
            if self._ffi_module is not None:
                rc = self._ffi_module.delete(key_bytes)
                return rc == 0
            if self._lib is not None:
                rc = self._lib.xstore_ffi_delete(key_bytes, len(key_bytes))
                return rc == 0
        except Exception as e:
            logger.warning("XSTORE delete failed for key %s: %s", key, e)
        return False

    def list_keys(self, prefix: str) -> List[str]:
        """List all keys matching a prefix. Returns empty list if unavailable."""
        if not self.available:
            return []
        # XSTORE cursor range scan: uses prefix as lower bound,
        # prefix + \xff as upper bound for the B-tree range query.
        prefix_bytes = prefix.encode("utf-8")
        upper_bytes = prefix_bytes + b"\xff"
        try:
            if self._ffi_module is not None and hasattr(self._ffi_module, "range_scan"):
                results = self._ffi_module.range_scan(prefix_bytes, upper_bytes, 10000)
                return [k.decode("utf-8", errors="replace") for k in results]
        except Exception as e:
            logger.warning("XSTORE list_keys failed for prefix %s: %s", prefix, e)
        return []


# Initialize global XSTORE backend at module load
_xstore_backend = XStoreBackend()


# ── M19: JSONL file-backed persistence fallback ─────────────────────────────
#
# When XSTORE is unavailable, SoulManager uses this JSONL journal backend
# for durable persistence.  Each PUT/DELETE operation is appended as a single
# JSON line.  On startup, the journal is replayed to reconstruct state.
#
# Per-agent namespace isolation: each agent gets its own JSONL file under
# {data_dir}/{agent}.jsonl so one agent's data cannot collide with another's.
#
# Values are stored as base64-encoded bytes (since they are already encrypted
# by the AES-GCM layer).

# Default path for JSONL persistence — configurable via env var.
_SOUL_JOURNAL_DIR = os.environ.get("SOUL_JOURNAL_DIR", "/tmp/genos/soul")


class _JournalBackend:
    """JSONL append-only journal for soul data persistence.

    Each mutation (PUT or DELETE) is appended as one JSON line:
        {"op": "PUT",    "key": "...", "value": "<base64>"}
        {"op": "DELETE", "key": "..."}

    On load, lines are replayed in order so the final state is correct.
    """

    def __init__(self, data_dir: str = _SOUL_JOURNAL_DIR) -> None:
        self._data_dir = data_dir
        os.makedirs(self._data_dir, exist_ok=True)
        logger.info("SoulManager JSONL journal dir: %s", self._data_dir)

    def _agent_from_key(self, storage_key: str) -> str:
        """Extract agent name from a storage key like soul:{agent}:{bucket}:{path}."""
        parts = storage_key.split(":", 3)
        if len(parts) >= 2:
            return parts[1]
        return "_default"

    def _journal_path(self, agent: str) -> str:
        """Return the JSONL file path for a given agent."""
        # Sanitize agent name for filesystem safety
        safe_name = agent.replace("/", "_").replace(":", "_").replace("..", "_")
        return os.path.join(self._data_dir, f"{safe_name}.jsonl")

    def load_all(self) -> dict[str, bytes]:
        """Replay all JSONL journals and return reconstructed key-value state.

        Returns a dict of storage_key -> encrypted_value (bytes).
        Called once at SoulManager init to restore persisted state.
        """
        state: dict[str, bytes] = {}
        if not os.path.isdir(self._data_dir):
            return state

        for filename in os.listdir(self._data_dir):
            if not filename.endswith(".jsonl"):
                continue
            filepath = os.path.join(self._data_dir, filename)
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    for line_no, line in enumerate(f, 1):
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            entry = json.loads(line)
                        except json.JSONDecodeError:
                            logger.warning(
                                "soul journal: corrupt line %d in %s — skipped",
                                line_no, filepath,
                            )
                            continue
                        op = entry.get("op", "")
                        key = entry.get("key", "")
                        if op == "PUT" and key:
                            value_b64 = entry.get("value", "")
                            try:
                                state[key] = base64.b64decode(value_b64)
                            except Exception:
                                logger.warning(
                                    "soul journal: bad base64 at line %d in %s",
                                    line_no, filepath,
                                )
                        elif op == "DELETE" and key:
                            state.pop(key, None)
            except OSError as e:
                logger.warning("soul journal: failed to read %s: %s", filepath, e)

        logger.info(
            "SoulManager: loaded %d keys from JSONL journal in %s",
            len(state), self._data_dir,
        )
        return state

    def append_put(self, storage_key: str, encrypted_value: bytes) -> None:
        """Append a PUT operation to the agent's JSONL journal."""
        agent = self._agent_from_key(storage_key)
        journal_path = self._journal_path(agent)
        entry = json.dumps({
            "op": "PUT",
            "key": storage_key,
            "value": base64.b64encode(encrypted_value).decode("ascii"),
        }, separators=(",", ":"))
        try:
            with open(journal_path, "a", encoding="utf-8") as f:
                f.write(entry + "\n")
                f.flush()
                os.fsync(f.fileno())
        except OSError as e:
            logger.warning("soul journal: PUT append failed for %s: %s", storage_key, e)

    def append_delete(self, storage_key: str) -> None:
        """Append a DELETE operation to the agent's JSONL journal."""
        agent = self._agent_from_key(storage_key)
        journal_path = self._journal_path(agent)
        entry = json.dumps({
            "op": "DELETE",
            "key": storage_key,
        }, separators=(",", ":"))
        try:
            with open(journal_path, "a", encoding="utf-8") as f:
                f.write(entry + "\n")
                f.flush()
                os.fsync(f.fileno())
        except OSError as e:
            logger.warning("soul journal: DELETE append failed for %s: %s", storage_key, e)


class SoulManager:
    """
    Soul (agent memory) manager with AES-256 encryption and layered persistence.

    Storage schema:
        _store[f"soul:{agent}:{bucket}:{sub_path}"] = encrypted(value)

    All methods enforce agent namespace isolation: an agent cannot
    read or write keys belonging to another agent.

    Sprint 38 fix (C4): All stored values are now encrypted at rest
    using per-agent derived keys. Cleartext never touches the store.

    Persistence layers (checked in order):
        1. XSTORE B-tree (native C library via ctypes) — production backend
        2. JSONL append-only journal — file-backed fallback (M19 fix)
        3. In-memory dict — always present as read cache

    On PUT: writes to dict AND appends to JSONL journal AND writes to XSTORE
    (if available).  On startup: replays JSONL journal into dict so state
    survives process restarts even without XSTORE.
    """

    def __init__(self, journal_dir: str = _SOUL_JOURNAL_DIR) -> None:
        self._store: dict[str, bytes] = {}
        self._lock = asyncio.Lock()
        self._xstore = _xstore_backend
        self._journal = _JournalBackend(data_dir=journal_dir)

        # M19: On init, if XSTORE is available, we don't preload all keys
        # into the dict cache — we lazily populate on get() misses.
        if self._xstore.available:
            logger.info(
                "SoulManager: XSTORE backend active — persistent storage enabled"
            )

        # M19: Replay JSONL journal into in-memory dict on startup.
        # This ensures state is recovered even when XSTORE is unavailable.
        journal_state = self._journal.load_all()
        if journal_state:
            self._store.update(journal_state)
            logger.info(
                "SoulManager: restored %d keys from JSONL journal", len(journal_state)
            )

    def _make_key(self, agent: str, bucket: str, sub_path: str) -> str:
        """Build a canonical storage key, validating inputs."""
        if not agent or "/" in agent or ":" in agent:
            raise SoulManagerError(f"Invalid agent name: {agent!r}")
        if bucket not in VALID_BUCKETS:
            raise SoulManagerError(
                f"Invalid bucket {bucket!r}. Must be one of {sorted(VALID_BUCKETS)}"
            )
        if not sub_path:
            raise SoulManagerError("sub_path must be non-empty")
        return f"soul:{agent}:{bucket}:{sub_path}"

    async def get(
        self,
        agent: str,
        bucket: str,
        sub_path: str,
    ) -> Optional[Any]:
        """
        Retrieve a value from the agent's soul bucket.

        Returns None if the key does not exist.
        Enforces agent namespace isolation — only the owning agent can read.
        """
        storage_key = self._make_key(agent, bucket, sub_path)
        async with self._lock:
            encrypted = self._store.get(storage_key)
        if encrypted is None and self._xstore.available:
            # M19: Cache miss — try XSTORE persistent backend
            xstore_val = self._xstore.get(storage_key)
            if xstore_val is not None:
                encrypted = xstore_val
                # Populate cache for subsequent reads
                async with self._lock:
                    self._store[storage_key] = encrypted
                logger.debug("soul.get %s -> <xstore hit>", storage_key)
        if encrypted is None:
            logger.debug("soul.get %s -> <miss>", storage_key)
            return None
        # Sprint 38 fix (C4): decrypt value using per-agent key
        agent_key = _derive_key(agent, _MASTER_SECRET)
        plaintext = _decrypt_value(encrypted, agent_key)
        if plaintext is None:
            logger.warning("soul.get %s -> <decrypt failed>", storage_key)
            return None
        logger.debug("soul.get %s -> <found>", storage_key)
        return json.loads(plaintext)

    async def put(
        self,
        agent: str,
        bucket: str,
        sub_path: str,
        value: Any,
    ) -> None:
        """
        Store a value in the agent's soul bucket.

        Enforces agent namespace isolation.
        """
        storage_key = self._make_key(agent, bucket, sub_path)
        # Sprint 38 fix (C4): encrypt value using per-agent key
        agent_key = _derive_key(agent, _MASTER_SECRET)
        plaintext = json.dumps(value, separators=(",", ":")).encode("utf-8")
        encrypted = _encrypt_value(plaintext, agent_key)
        async with self._lock:
            self._store[storage_key] = encrypted
        # M19: Write-through to XSTORE persistent backend
        if self._xstore.available:
            ok = self._xstore.put(storage_key, encrypted)
            if not ok:
                logger.warning(
                    "soul.put %s — XSTORE write-through failed", storage_key
                )
        # M19: Append to JSONL journal for file-backed persistence
        self._journal.append_put(storage_key, encrypted)
        logger.debug("soul.put %s (%d bytes encrypted)", storage_key, len(encrypted))

    async def list_keys(
        self,
        agent: str,
        bucket: str,
        prefix: str = "",
    ) -> List[str]:
        """
        List all sub_path keys for this agent+bucket matching prefix.

        Returns a list of sub_path strings (not full storage keys).
        Enforces agent namespace isolation.
        """
        if bucket not in VALID_BUCKETS:
            raise SoulManagerError(
                f"Invalid bucket {bucket!r}. Must be one of {sorted(VALID_BUCKETS)}"
            )
        namespace_prefix = f"soul:{agent}:{bucket}:"
        full_prefix = namespace_prefix + prefix
        async with self._lock:
            matching = set(
                key[len(namespace_prefix):]
                for key in self._store
                if key.startswith(full_prefix)
            )
        # M19: Merge keys from XSTORE persistent backend
        if self._xstore.available:
            xstore_keys = self._xstore.list_keys(full_prefix)
            for xk in xstore_keys:
                if xk.startswith(namespace_prefix):
                    matching.add(xk[len(namespace_prefix):])
        return sorted(matching)

    async def delete(
        self,
        agent: str,
        bucket: str,
        sub_path: str,
    ) -> bool:
        """
        Delete a key from the agent's soul bucket.

        Returns True if the key existed, False otherwise.
        """
        key = self._make_key(agent, bucket, sub_path)
        async with self._lock:
            existed = key in self._store
            if existed:
                del self._store[key]
        # M19: Delete from XSTORE persistent backend
        if self._xstore.available:
            self._xstore.delete(key)
        # M19: Append DELETE to JSONL journal for file-backed persistence
        if existed:
            self._journal.append_delete(key)
        logger.debug(f"soul.delete {key} -> {'deleted' if existed else 'not found'}")
        return existed

    async def agent_stats(self, agent: str) -> Dict[str, int]:
        """Return per-bucket key counts for an agent."""
        stats: Dict[str, int] = {b: 0 for b in VALID_BUCKETS}
        async with self._lock:
            for key in self._store:
                parts = key.split(":", 3)
                if len(parts) == 4 and parts[1] == agent:
                    bucket = parts[2]
                    if bucket in stats:
                        stats[bucket] += 1
        return stats
