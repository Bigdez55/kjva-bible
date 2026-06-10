"""
byte_codec.py — the ONE canonical byte<->token-id codec for the Tokenless byte-LM.

Source of truth: the pretrainer `train_byte.py` tokenizes as
    np.frombuffer(raw, uint8).astype(uint16) + 3
i.e. raw byte b -> token id (b + byte_offset), with byte_offset reserving ids
0/1/2 for PAD/BOS/EOS. For the canonical model vocab_size=259 => byte_offset=3,
so bytes map to ids 3..258.

EVERY training / eval / serving path MUST encode through this module. The prior
`load_corpus_tokens` used `b + 1`, shifting every token by 2 into the BOS/EOS
range — a trained base fed `b+1` mispredicts confidently (held-out BPB 14.2 vs
1.17) and emits garbage. That bug poisoned every flat PEFT/SFT/DPO run that went
through `load_corpus_tokens` (the likely cause of the v1 `corejtcy` noise).

Do NOT hardcode `+ 1` or `+ 3` anywhere else. Call these functions.
"""
from __future__ import annotations

PAD_ID = 0
BOS_ID = 1
EOS_ID = 2


def byte_offset(vocab_size: int = 259) -> int:
    """Special-token count = vocab_size - 256. Canonical model => 3."""
    off = vocab_size - 256
    if off < 1:
        raise ValueError(
            f"vocab_size={vocab_size} leaves no room for special tokens "
            f"(need >= 257; byte_offset would be {off})")
    return off


def encode_bytes(data: bytes, vocab_size: int = 259) -> list[int]:
    """Raw bytes -> token ids (b + byte_offset). No BOS/EOS added."""
    off = byte_offset(vocab_size)
    return [b + off for b in data]


def encode_text(text: str, vocab_size: int = 259, add_bos: bool = False) -> list[int]:
    """UTF-8 text -> token ids. Optionally prepend BOS (fresh-context convention)."""
    ids = encode_bytes(text.encode("utf-8"), vocab_size)
    return ([BOS_ID] + ids) if add_bos else ids


def decode_ids(ids, vocab_size: int = 259, errors: str = "replace") -> str:
    """Token ids -> UTF-8 text. Drops PAD/BOS/EOS and any out-of-range id."""
    off = byte_offset(vocab_size)
    raw = bytes(t - off for t in ids if off <= t < off + 256)
    return raw.decode("utf-8", errors)
