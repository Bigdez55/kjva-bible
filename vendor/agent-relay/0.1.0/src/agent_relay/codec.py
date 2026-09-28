"""Canonical JSON, bounded lossless compression, and portable path validation."""
from __future__ import annotations
import base64
import hashlib
import json
import math
import re
import unicodedata
import zlib
from pathlib import PurePosixPath
from typing import Any
from .errors import RelayError, require

MAX_BLOB = 32 * 1024 * 1024
MAX_REQUEST = 4 * 1024 * 1024
ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,95}\Z")
SECRET_NAMES = {".env", "id_rsa", "id_ed25519", "owner.key", "credentials.json"}
DENIED_PARTS = {".git", ".agent-relay", ".byte", ".byte-orchestration"}


def canonical(value: Any) -> bytes:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True,
                          separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as e:
        raise RelayError("INVALID_JSON", str(e)) from e


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def object_digest(value: Any) -> str:
    return digest(canonical(value))


def strict_loads(data: str | bytes) -> Any:
    def pairs(items):
        out = {}
        for key, value in items:
            require(key not in out, "DUPLICATE_KEY", key)
            out[key] = value
        return out
    try:
        return json.loads(data, object_pairs_hook=pairs,
                          parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))
    except (ValueError, UnicodeError) as e:
        raise RelayError("INVALID_JSON", str(e)) from e


def text(value: Any, name: str, limit: int = 65536) -> str:
    require(type(value) is str and bool(value.strip()) and len(value.encode("utf-8")) <= limit,
            "INVALID_FIELD", f"{name}: expected nonempty text <= {limit} UTF-8 bytes")
    require("\x00" not in value, "INVALID_FIELD", f"{name}: NUL forbidden")
    return value


def ident(value: Any, name: str = "id") -> str:
    require(type(value) is str and ID_RE.fullmatch(value) is not None,
            "INVALID_ID", f"{name}: use 1..96 ASCII letters, digits, dot, hyphen, underscore")
    return value


def integer(value: Any, name: str, lo: int, hi: int) -> int:
    require(type(value) is int and lo <= value <= hi, "INVALID_FIELD", f"{name}: {lo}..{hi}")
    return value


def number(value: Any, name: str, lo: float, hi: float) -> float:
    require(type(value) in (float, int) and math.isfinite(value) and lo <= value <= hi,
            "INVALID_FIELD", f"{name}: {lo}..{hi}")
    return float(value)


def string_list(value: Any, name: str, max_count: int = 128) -> list[str]:
    require(type(value) is list and len(value) <= max_count, "INVALID_FIELD", f"{name}: list required")
    result = [text(x, name, 4096) for x in value]
    require(len(result) == len(set(result)), "DUPLICATE", name)
    return result


def relpath(value: Any) -> str:
    value = text(value, "path", 2048)
    p = PurePosixPath(value)
    require(not p.is_absolute() and str(p) == value and "\\" not in value
            and ".." not in p.parts and value not in (".", "")
            and unicodedata.normalize("NFC", value) == value,
            "UNSAFE_PATH", "path must be canonical relative POSIX NFC, without aliases or traversal")
    require(not any(x in DENIED_PARTS for x in p.parts), "UNSAFE_PATH", "control and Git paths are protected")
    require(not any(x in SECRET_NAMES or x.startswith(".env.") or x.endswith((".pem", ".key"))
                    for x in p.parts), "SENSITIVE_PATH", "secret-bearing path is not transferable")
    return value


def resource(value: Any) -> str:
    value = text(value, "resource", 2048)
    require(not value.startswith("/") and "\\" not in value
            and all(x and x not in (".", "..") for x in value.split("/")),
            "INVALID_RESOURCE", value)
    return value.casefold() if value.startswith("repo/") else value


def overlaps(a: str, b: str) -> bool:
    return a == b or a.startswith(b + "/") or b.startswith(a + "/")


def encode_blob(raw: bytes) -> tuple[str, bytes]:
    require(type(raw) is bytes and len(raw) <= MAX_BLOB, "BLOB_LIMIT", "blob exceeds 32 MiB")
    compressed = zlib.compress(raw, 6)
    return ("zlib", compressed) if len(compressed) < len(raw) else ("raw", raw)


def decode_blob(codec: str, data: bytes, size: int, expected: str) -> bytes:
    require(0 <= size <= MAX_BLOB, "CORRUPT_BLOB", "invalid decoded length")
    if codec == "raw":
        raw = data
    elif codec == "zlib":
        decoder = zlib.decompressobj()
        try:
            raw = decoder.decompress(data, size + 1)
            require(decoder.eof and not decoder.unused_data and not decoder.unconsumed_tail,
                    "CORRUPT_BLOB", "noncanonical or oversized compressed stream")
        except zlib.error as e:
            raise RelayError("CORRUPT_BLOB", str(e)) from e
    else:
        raise RelayError("CORRUPT_BLOB", "unknown codec")
    require(len(raw) == size and digest(raw) == expected, "CORRUPT_BLOB", "content hash/size mismatch")
    return raw


def unb64(value: Any) -> bytes:
    require(type(value) is str, "INVALID_FIELD", "data_b64 must be a string")
    try:
        raw = base64.b64decode(value, validate=True)
    except (ValueError, TypeError) as e:
        raise RelayError("INVALID_FIELD", "invalid base64") from e
    require(len(raw) <= MAX_BLOB, "BLOB_LIMIT", "too large")
    return raw
