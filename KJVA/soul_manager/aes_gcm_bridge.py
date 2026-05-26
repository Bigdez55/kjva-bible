"""council/runtime/memory/aes_gcm_bridge.py
AES-256-GCM bridge for the Council memory layer.

Provides two public functions — aes_gcm_encrypt / aes_gcm_decrypt — with a
strict two-tier strategy:

  Tier 1 (preferred): ctypes FFI to xsec_aes_gcm_encrypt / xsec_aes_gcm_decrypt
  in the XSEC shared library (libxsec.so or libxsec.dylib).

  Tier 2 (development fallback): Python 'cryptography' package
  (AEADBad), which provides real AES-256-GCM.  THIS IS NOT A
  placeholder; it is a fully authenticated cipher.

  NO SHA-256 XOR FALLBACK.  If neither tier is available, every
  encrypt / decrypt call raises AesGcmUnavailable.  Silent
  downgrade to unauthenticated crypto is a security violation.

Production note:
  Set XSEC_LIB_PATH to the absolute path of libxsec.so/.dylib to
  activate Tier 1.  Without it, Tier 2 is used when the
  'cryptography' package is importable.

  Set TOKENLESS_STRICT_CRYPTO=1 to force Tier 1 only and hard-fail if
  the native library is unavailable (recommended for production ISO).

C signatures (sec/xsec/crypto/aes_gcm.c):

  xsec_status_t xsec_aes_gcm_encrypt(
      const uint8_t key[32], const uint8_t nonce[12],
      const uint8_t *aad, size_t aad_len,
      const uint8_t *pt,  size_t pt_len,
      uint8_t *ct, uint8_t tag[16]);

  xsec_status_t xsec_aes_gcm_decrypt(
      const uint8_t key[32], const uint8_t nonce[12],
      const uint8_t *aad, size_t aad_len,
      const uint8_t *ct,  size_t ct_len,
      const uint8_t tag[16], uint8_t *pt);

  xsec_status_t is int32_t; XSEC_OK = 0.

Copyright (c) 2026 Tokenless Models Project. All rights reserved.
SPDX-License-Identifier: LicenseRef-Proprietary
"""
from __future__ import annotations

import ctypes
import logging
import os
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Sentinel exception — raised when no valid cipher backend is available.
# ---------------------------------------------------------------------------

class AesGcmUnavailable(RuntimeError):
    """Raised when neither the native xsec library nor the Python
    cryptography package is available.  Callers MUST NOT continue
    with unprotected storage."""


# ---------------------------------------------------------------------------
# Internal state
# ---------------------------------------------------------------------------

_XSEC_OK: int = 0

_xsec_lib: Optional[ctypes.CDLL] = None
_xsec_encrypt_fn: Optional[ctypes.CDLL] = None
_xsec_decrypt_fn: Optional[ctypes.CDLL] = None
_python_aesgcm: Optional[object] = None   # cryptography.hazmat AESGCM class

# Set once at module load; callers can re-call _init() after setting env vars.
_initialised: bool = False


def _init() -> None:
    """Attempt to bind both backends.  Called once at module import."""
    global _xsec_lib, _xsec_encrypt_fn, _xsec_decrypt_fn
    global _python_aesgcm, _initialised

    strict = os.environ.get("TOKENLESS_STRICT_CRYPTO", "0").strip() == "1"

    # -- Tier 1: native xsec shared library ----------------------------------
    lib_env = os.environ.get("XSEC_LIB_PATH", "").strip()
    search_paths: list[str] = []
    if lib_env:
        search_paths.append(lib_env)

    _project_root = Path(__file__).resolve().parents[3]
    for suffix in ("libxsec.so", "libxsec.dylib"):
        search_paths.append(str(_project_root / "build" / "xsec" / suffix))
        search_paths.append(str(_project_root / "sec" / "xsec" / suffix))
        search_paths.append("/usr/local/lib/" + suffix)
        search_paths.append("/usr/lib/" + suffix)

    for lib_path in search_paths:
        if not lib_path:
            continue
        try:
            lib = ctypes.CDLL(lib_path)
        except OSError:
            continue

        try:
            enc = lib.xsec_aes_gcm_encrypt
            enc.restype = ctypes.c_int32
            enc.argtypes = [
                ctypes.c_char_p,   # key[32]
                ctypes.c_char_p,   # nonce[12]
                ctypes.c_char_p,   # aad  (may be NULL)
                ctypes.c_size_t,   # aad_len
                ctypes.c_char_p,   # pt
                ctypes.c_size_t,   # pt_len
                ctypes.c_char_p,   # ct (output, caller-allocated)
                ctypes.c_char_p,   # tag[16] (output)
            ]

            dec = lib.xsec_aes_gcm_decrypt
            dec.restype = ctypes.c_int32
            dec.argtypes = [
                ctypes.c_char_p,   # key[32]
                ctypes.c_char_p,   # nonce[12]
                ctypes.c_char_p,   # aad  (may be NULL)
                ctypes.c_size_t,   # aad_len
                ctypes.c_char_p,   # ct
                ctypes.c_size_t,   # ct_len
                ctypes.c_char_p,   # tag[16]
                ctypes.c_char_p,   # pt (output, caller-allocated)
            ]

            _xsec_lib = lib
            _xsec_encrypt_fn = enc
            _xsec_decrypt_fn = dec
            logger.info("aes_gcm_bridge: Tier 1 (xsec native) bound from %s", lib_path)
            _initialised = True
            return
        except AttributeError as exc:
            logger.debug(
                "aes_gcm_bridge: %s loaded but missing AES-GCM symbols: %s",
                lib_path, exc,
            )

    # Tier 1 unavailable.
    if strict:
        raise AesGcmUnavailable(
            "TOKENLESS_STRICT_CRYPTO=1: xsec shared library not found. "
            "Set XSEC_LIB_PATH to the path of libxsec.so/.dylib."
        )

    logger.warning(
        "aes_gcm_bridge: xsec native library not found — trying Python 'cryptography' (Tier 2). "
        "Set XSEC_LIB_PATH for production use. Set TOKENLESS_STRICT_CRYPTO=1 to hard-fail."
    )

    # -- Tier 2: Python cryptography package ---------------------------------
    try:
        from cryptography.hazmat.primitives.ciphers.aead import (
            AESGCM as _AESGCM,  # type: ignore[import]
        )
        _python_aesgcm = _AESGCM
        logger.info("aes_gcm_bridge: Tier 2 (Python cryptography AESGCM) active.")
        _initialised = True
        return
    except ImportError:
        pass

    # Neither tier available — caller will receive AesGcmUnavailable on use.
    logger.error(
        "aes_gcm_bridge: NO AES-GCM backend available. "
        "Install 'cryptography' package or provide libxsec.so via XSEC_LIB_PATH. "
        "All encrypt/decrypt calls will raise AesGcmUnavailable."
    )
    _initialised = True


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def aes_gcm_encrypt(
    key: bytes,
    nonce: bytes,
    plaintext: bytes,
    aad: bytes = b"",
) -> Tuple[bytes, bytes]:
    """Encrypt *plaintext* with AES-256-GCM.

    Args:
        key:       32-byte AES-256 key.
        nonce:     12-byte GCM nonce.  MUST be unique per (key, message).
        plaintext: Data to encrypt (arbitrary length).
        aad:       Additional authenticated data (not encrypted).

    Returns:
        (ciphertext, tag) — tag is 16 bytes.

    Raises:
        ValueError:          If key or nonce are the wrong length.
        AesGcmUnavailable:   If no cipher backend is available.
        RuntimeError:        If the native xsec function returns an error code.
    """
    if not _initialised:
        _init()

    if len(key) != 32:
        raise ValueError(f"aes_gcm_encrypt: key must be 32 bytes, got {len(key)}")
    if len(nonce) != 12:
        raise ValueError(f"aes_gcm_encrypt: nonce must be 12 bytes, got {len(nonce)}")

    # Tier 1: native xsec
    if _xsec_encrypt_fn is not None:
        ct_buf = ctypes.create_string_buffer(len(plaintext))
        tag_buf = ctypes.create_string_buffer(16)
        aad_ptr = aad if aad else None
        rc: int = _xsec_encrypt_fn(
            key, nonce,
            aad_ptr, len(aad),
            plaintext, len(plaintext),
            ct_buf, tag_buf,
        )
        if rc != _XSEC_OK:
            raise RuntimeError(f"xsec_aes_gcm_encrypt returned error code {rc}")
        return ct_buf.raw, tag_buf.raw

    # Tier 2: Python cryptography
    if _python_aesgcm is not None:
        aesgcm = _python_aesgcm(key)
        combined = aesgcm.encrypt(nonce, plaintext, aad if aad else None)
        # cryptography returns ciphertext + 16-byte tag concatenated
        ciphertext = combined[:-16]
        tag = combined[-16:]
        return ciphertext, tag

    raise AesGcmUnavailable(
        "No AES-GCM backend is available. "
        "Install 'cryptography' package or set XSEC_LIB_PATH."
    )


def aes_gcm_decrypt(
    key: bytes,
    nonce: bytes,
    ciphertext: bytes,
    tag: bytes,
    aad: bytes = b"",
) -> bytes:
    """Decrypt and authenticate *ciphertext* with AES-256-GCM.

    Args:
        key:        32-byte AES-256 key.
        nonce:      12-byte GCM nonce used during encryption.
        ciphertext: Encrypted data.
        tag:        16-byte authentication tag.
        aad:        Additional authenticated data (same value used at encrypt).

    Returns:
        Plaintext bytes.

    Raises:
        ValueError:          If key, nonce, or tag are the wrong length.
        AesGcmUnavailable:   If no cipher backend is available.
        RuntimeError:        If authentication fails (tag mismatch) or the
                             native xsec function returns an error code.
    """
    if not _initialised:
        _init()

    if len(key) != 32:
        raise ValueError(f"aes_gcm_decrypt: key must be 32 bytes, got {len(key)}")
    if len(nonce) != 12:
        raise ValueError(f"aes_gcm_decrypt: nonce must be 12 bytes, got {len(nonce)}")
    if len(tag) != 16:
        raise ValueError(f"aes_gcm_decrypt: tag must be 16 bytes, got {len(tag)}")

    # Tier 1: native xsec
    if _xsec_decrypt_fn is not None:
        pt_buf = ctypes.create_string_buffer(len(ciphertext))
        aad_ptr = aad if aad else None
        rc: int = _xsec_decrypt_fn(
            key, nonce,
            aad_ptr, len(aad),
            ciphertext, len(ciphertext),
            tag, pt_buf,
        )
        if rc != _XSEC_OK:
            raise RuntimeError(
                f"xsec_aes_gcm_decrypt returned error code {rc} "
                "(authentication failure or invalid parameters)"
            )
        return pt_buf.raw

    # Tier 2: Python cryptography
    if _python_aesgcm is not None:
        from cryptography.exceptions import InvalidTag  # type: ignore[import]
        aesgcm = _python_aesgcm(key)
        try:
            return aesgcm.decrypt(nonce, ciphertext + tag, aad if aad else None)
        except InvalidTag as exc:
            raise RuntimeError("AES-GCM authentication failure: tag mismatch") from exc

    raise AesGcmUnavailable(
        "No AES-GCM backend is available. "
        "Install 'cryptography' package or set XSEC_LIB_PATH."
    )


def backend_name() -> str:
    """Return a human-readable label for the active backend."""
    if not _initialised:
        _init()
    if _xsec_encrypt_fn is not None:
        return "xsec-native"
    if _python_aesgcm is not None:
        return "python-cryptography"
    return "unavailable"


# Initialise on import.
_init()
