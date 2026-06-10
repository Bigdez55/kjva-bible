"""test_byte_sft_architecture.py — P-12: byte-level SFT artifact has canonical architecture.

Closure standard (from sprint handoff):
  A canonical-compatible byte-level SFT artifact exists and is verified as
  vocab_size=259, n_layers=8.

Negative test: the BPE sft_v1 artifact must NOT pass the canonical check.
  This proves the guard distinguishes good artifacts from the old bad one.

Run:  python3 -m pytest tests/test_byte_sft_architecture.py -q
"""
import json
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
# ml-training is a sibling of the substrate tree when nested in the source repo
# (_REPO_ROOT.parent/ml-training) and a child of the tree root when deployed flat
# as the KJVA project (_REPO_ROOT/ml-training). Resolve across both layouts.
_ML_TRAINING = next(
    (p for p in (_REPO_ROOT.parent / "ml-training", _REPO_ROOT / "ml-training") if p.exists()),
    _REPO_ROOT.parent / "ml-training",
)

_BYTE_SFT_RUN = _ML_TRAINING / "runs" / "byte_sft_v1"
_BYTE_SFT_CONFIG = _BYTE_SFT_RUN / "model_config.json"
_BYTE_SFT_WEIGHTS = _BYTE_SFT_RUN / "model_weights.npz"

_BPE_SFT_RUN = _ML_TRAINING / "runs" / "sft_v1"
_BPE_SFT_CONFIG = _BPE_SFT_RUN / "model_config.json"
_BPE_SFT_GGUF_JSON = _BPE_SFT_RUN / "gguf" / "sft_v1.gguf.json"

CANONICAL_VOCAB = 259
CANONICAL_LAYERS = 8


def _load_config(path: Path) -> dict:
    with open(path) as f:
        return json.load(f)


# ── Positive tests ─────────────────────────────────────────────────────────────

def test_byte_sft_run_exists():
    """byte_sft_v1 run directory and weights must exist."""
    assert _BYTE_SFT_RUN.exists(), (
        f"byte_sft_v1 run directory not found: {_BYTE_SFT_RUN}. "
        "Run: train_peft.py --method sft --model-config <canonical> "
        "--base-checkpoint <kjva_weights>"
    )
    assert _BYTE_SFT_WEIGHTS.exists(), (
        f"byte_sft_v1 weights not found: {_BYTE_SFT_WEIGHTS}"
    )


def test_byte_sft_config_exists():
    """byte_sft_v1 model_config.json must exist alongside weights."""
    if not _BYTE_SFT_RUN.exists():
        pytest.skip(f"byte_sft_v1 not yet trained: {_BYTE_SFT_RUN}")
    assert _BYTE_SFT_CONFIG.exists(), (
        f"model_config.json not found in byte_sft_v1: {_BYTE_SFT_CONFIG}"
    )


def test_byte_sft_vocab_size_is_259():
    """byte_sft_v1 model_config.json must declare vocab_size=259."""
    if not _BYTE_SFT_CONFIG.exists():
        pytest.skip(f"byte_sft_v1 config not yet created: {_BYTE_SFT_CONFIG}")
    cfg = _load_config(_BYTE_SFT_CONFIG)
    assert cfg.get("vocab_size") == CANONICAL_VOCAB, (
        f"vocab_size mismatch: expected {CANONICAL_VOCAB}, got {cfg.get('vocab_size')}. "
        "SFT was not trained on the canonical byte-level architecture."
    )


def test_byte_sft_n_layers_is_8():
    """byte_sft_v1 model_config.json must declare n_layers=8."""
    if not _BYTE_SFT_CONFIG.exists():
        pytest.skip(f"byte_sft_v1 config not yet created: {_BYTE_SFT_CONFIG}")
    cfg = _load_config(_BYTE_SFT_CONFIG)
    assert cfg.get("n_layers") == CANONICAL_LAYERS, (
        f"n_layers mismatch: expected {CANONICAL_LAYERS}, got {cfg.get('n_layers')}. "
        "SFT was not trained on the canonical byte-level architecture."
    )


def test_byte_sft_canonical_compatible_flag():
    """byte_sft_v1 model_config.json must have canonical_compatible=true."""
    if not _BYTE_SFT_CONFIG.exists():
        pytest.skip(f"byte_sft_v1 config not yet created: {_BYTE_SFT_CONFIG}")
    cfg = _load_config(_BYTE_SFT_CONFIG)
    assert cfg.get("canonical_compatible") is True, (
        f"canonical_compatible flag is {cfg.get('canonical_compatible')!r} — expected true. "
        "Config: {cfg}"
    )


# ── Negative test ──────────────────────────────────────────────────────────────

def test_bpe_sft_v1_fails_canonical_check():
    """The old BPE sft_v1 artifact must NOT pass the canonical byte-level check.

    If no sft_v1/model_config.json exists, look for the GGUF json which records
    the architecture from the original run.
    """
    if _BPE_SFT_CONFIG.exists():
        cfg = _load_config(_BPE_SFT_CONFIG)
    elif _BPE_SFT_GGUF_JSON.exists():
        with open(_BPE_SFT_GGUF_JSON) as f:
            raw = json.load(f)
        cfg = raw.get("model_config", raw.get("config", raw))
    else:
        pytest.skip(
            f"BPE sft_v1 config not found at {_BPE_SFT_CONFIG} or {_BPE_SFT_GGUF_JSON} "
            "— cannot run negative test"
        )

    is_canonical_vocab = cfg.get("vocab_size") == CANONICAL_VOCAB
    is_canonical_layers = cfg.get("n_layers") == CANONICAL_LAYERS

    assert not (is_canonical_vocab and is_canonical_layers), (
        "BPE sft_v1 config unexpectedly passes canonical byte-level check — "
        f"vocab_size={cfg.get('vocab_size')}, n_layers={cfg.get('n_layers')}. "
        "Investigate: was sft_v1 actually trained with the byte-level architecture?"
    )
