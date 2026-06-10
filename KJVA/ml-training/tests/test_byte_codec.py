"""
Regression tests for the canonical byte codec (byte_codec.py).

Locks the byte_offset=3 invariant that the base was pretrained with
(train_byte.py: bytes map to 3..258). Guards against the `b + 1` regression that
poisoned every flat PEFT/SFT/DPO run via load_corpus_tokens.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from byte_codec import (  # noqa: E402
    byte_offset, encode_bytes, encode_text, decode_ids, PAD_ID, BOS_ID, EOS_ID,
)


def test_byte_offset_canonical():
    """vocab_size=259 => byte_offset=3 (256 bytes + pad/bos/eos)."""
    assert byte_offset(259) == 3


def test_byte_0_maps_to_3():
    assert encode_bytes(bytes([0])) == [3]


def test_byte_255_maps_to_258():
    assert encode_bytes(bytes([255])) == [258]


def test_special_ids_reserved():
    """pad/bos/eos remain 0/1/2 and never collide with any byte id (>=3)."""
    assert (PAD_ID, BOS_ID, EOS_ID) == (0, 1, 2)
    ids = encode_bytes(bytes(range(256)))
    assert min(ids) == 3 and max(ids) == 258
    assert PAD_ID not in ids and BOS_ID not in ids and EOS_ID not in ids


def test_not_plus_one_regression():
    """The historic bug: byte b -> b+1. Must NOT happen for the canonical vocab."""
    assert encode_bytes(b"A") == [ord("A") + 3]
    assert encode_bytes(b"A") != [ord("A") + 1]


def test_roundtrip_text():
    text = "GEN 1:1 In the beginning God created the heaven and the earth."
    assert decode_ids(encode_text(text)) == text


def test_bos_prepend_optional():
    ids = encode_text("AB", add_bos=True)
    assert ids[0] == BOS_ID
    assert ids[1:] == [ord("A") + 3, ord("B") + 3]
    # decode drops BOS
    assert decode_ids(ids) == "AB"


def test_offset_scales_with_vocab():
    """A non-canonical vocab (e.g. 258 = 256 + 2 specials) yields offset 2."""
    assert byte_offset(258) == 2
    assert encode_bytes(bytes([0]), vocab_size=258) == [2]


def test_rejects_too_small_vocab():
    import pytest
    with pytest.raises(ValueError):
        byte_offset(256)
