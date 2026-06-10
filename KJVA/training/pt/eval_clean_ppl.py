#!/usr/bin/env python3
"""pt/eval_clean_ppl.py — score any TokenlessLM checkpoint on a fixed token set,
using the EXACT benchmark methodology that produced full_val_ppl=3.2125, so the
old benchmark model and the new clean model can be compared head-to-head on the
*same* held-out scripture.

Loaders (dispatch on extension/magic):
  *.safetensors  -> safetensors.torch.load_file  (new clean checkpoints)
  *.npz          -> dict of pt state_dict keys    (old GGUF export source — lossless)
  *.gguf         -> parse + REVERSE name-map -> pt state_dict  (export-contract proof)

Perplexity = exp( sum(next-byte NLL over non-overlapping seq_len chunks) / tokens ).
Token contract: byte -> byte+3 (PAD0/BOS1/EOS2 reserved); raw stream, no BOS/EOS inserted.

Subcommands:
  score    --checkpoint P --val {clean|marker|PATH}        # ppl of one model on one set
  compare  --old P_npz --new P_safetensors --val clean     # head-to-head, same tokens
  gate-a   --gguf G --npz N                                 # loader: GGUF-reverse == npz (allclose)
  gate-b   --checkpoint P [--expect 3.2125]                # scorer+identity: marker ppl in band

Verified facts (see cross-eval-harness-spec workflow):
  - kjv_byte.gguf is all-F32 (lossless), 74 tensors, exported from kjv_byte_bringup/weights.npz
  - weights.npz keys ARE pt/model.py state_dict keys (direct load, no remap)
  - marker corpus sha256 must be 0c498787...beec or the marker val window is wrong
"""
from __future__ import annotations

import argparse
import hashlib
import math
import struct
import sys
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F

SCRIPT_DIR = Path(__file__).resolve().parent              # training/pt
sys.path.insert(0, str(SCRIPT_DIR))
from model import ModelConfig, TokenlessLM                # noqa: E402

TRAINING_DIR = SCRIPT_DIR.parent                          # models v7/training
REPO_ROOT = TRAINING_DIR.parent.parent                    # Tokenless models

CLEAN_CACHE = TRAINING_DIR / "corpus" / "eng_kjv_clean_v1" / "tokens_byte_uint16.npy"
MARKER_CORPUS = REPO_ROOT / "ml-training" / "corpus" / "eng_kjv_apocrypha_v1" / "corpus.txt"
MARKER_SHA256 = "0c498787091aa1e80ede06cc533fc484813d231f3ffe8b99c26f6365bdeebaec"

# ── token sets ────────────────────────────────────────────────────────────────

def make_split(tokens: np.ndarray, valid_frac: float = 0.02):
    """IDENTICAL to train_byte.make_split — contiguous last 2%, no shuffle."""
    n_valid = max(4096, int(len(tokens) * valid_frac))
    return tokens[:-n_valid], tokens[-n_valid:]


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_val(name: str) -> tuple[np.ndarray, str]:
    """Return (val_tokens uint16, label). 'clean'|'marker'|<path to .npy>."""
    if name == "clean":
        arr = np.asarray(np.load(CLEAN_CACHE), dtype=np.uint16)
        _, val = make_split(arr)
        return val, f"clean_val[{len(val)}]"
    if name == "marker":
        got = _sha256(MARKER_CORPUS)
        if got != MARKER_SHA256:
            raise SystemExit(
                f"FATAL: marker corpus sha256 {got[:12]} != {MARKER_SHA256[:12]} — "
                "the marker val window would not match the published 3.2125 run; aborting.")
        raw = MARKER_CORPUS.read_bytes()
        arr = (np.frombuffer(raw, dtype=np.uint8).astype(np.uint16) + 3)   # byte+3, no framing
        _, val = make_split(arr)
        return val, f"marker_val[{len(val)}]"
    p = Path(name)
    arr = np.asarray(np.load(p), dtype=np.uint16)
    _, val = make_split(arr)
    return val, f"{p.name}_val[{len(val)}]"

# ── GGUF reverse-loader (export-contract proof) ─────────────────────────────────

_GGUF_VTYPES = {0: "B", 1: "b", 2: "H", 3: "h", 4: "I", 5: "i", 6: "f",
                7: "?", 10: "Q", 11: "q", 12: "d"}        # scalar struct codes
_GGML_DSIZE = {0: 4, 1: 2}                                 # F32, F16


def _dequant_q4_0(raw: bytes, nblocks: int) -> np.ndarray:
    """Match this repo's exporter (scripts/convert_to_gguf.quantize_q4_0), NOT stock ggml:
    18-byte block = f16 absmax scale + 16 packed bytes; nibbles are INTERLEAVED
    (even elem -> low nibble of byte k, odd elem -> high nibble); quant in [1,15] shifted
    from [-7,7]; dequant x = (q - 8)/7 * absmax."""
    b = np.frombuffer(raw, dtype=np.uint8).reshape(nblocks, 18)
    d = b[:, :2].copy().view(np.float16).reshape(nblocks, 1).astype(np.float32)   # step = absmax/7
    qs = b[:, 2:]                                          # (nblocks, 16) packed
    lo = (qs & 0x0F).astype(np.float32)                    # even-index quants_f
    hi = ((qs >> 4) & 0x0F).astype(np.float32)             # odd-index quants_f
    out = np.empty((nblocks, 32), dtype=np.float32)
    out[:, 0::2] = (lo - 8.0) * d                          # w = (nibble-8)*step (matches C engine)
    out[:, 1::2] = (hi - 8.0) * d
    return out.reshape(-1)


def _rev_name(gguf_name: str) -> str:
    """GGUF tensor name -> pt/model.py state_dict key (no transpose, direct assign)."""
    # token_embd = old MLX pipeline GGUF; token_emb = models v7 pipeline GGUF (interp_tokenless.c)
    m = {"token_embd.weight": "embed.weight", "token_emb.weight": "embed.weight",
         "output_norm.weight": "norm_final.weight"}
    if gguf_name in m:
        return m[gguf_name]
    # blk.N.<role>.weight -> blocks.N.<pt>.weight
    parts = gguf_name.split(".")
    assert parts[0] == "blk", f"unexpected GGUF tensor {gguf_name}"
    n, role = parts[1], parts[2]
    role_map = {
        "attn_norm": "norm1", "attn_q": "attn.q", "attn_k": "attn.k",
        "attn_v": "attn.v", "attn_output": "attn.o", "ffn_norm": "norm2",
        "ffn_gate": "mlp.gate", "ffn_up": "mlp.up", "ffn_down": "mlp.down",
    }
    return f"blocks.{n}.{role_map[role]}.weight"


def _read_gguf_str(buf, off):
    (ln,) = struct.unpack_from("<Q", buf, off); off += 8
    s = buf[off:off + ln].decode("utf-8"); off += ln
    return s, off


def _skip_gguf_value(buf, off, vtype):
    if vtype == 8:                                         # string
        _, off = _read_gguf_str(buf, off); return off
    if vtype == 9:                                         # array
        (et,) = struct.unpack_from("<I", buf, off); off += 4
        (ln,) = struct.unpack_from("<Q", buf, off); off += 8
        for _ in range(ln):
            off = _skip_gguf_value(buf, off, et)
        return off
    code = _GGUF_VTYPES[vtype]
    return off + struct.calcsize("<" + code)


def parse_gguf(path: Path) -> tuple[dict, dict]:
    """Return (state_dict-like {pt_key: np.float32 array}, metadata {key: name/align})."""
    buf = path.read_bytes()
    assert buf[:4] == b"GGUF", "not a GGUF file"
    ver, = struct.unpack_from("<I", buf, 4)
    n_tensors, = struct.unpack_from("<Q", buf, 8)
    n_kv, = struct.unpack_from("<Q", buf, 16)
    off = 24
    meta = {"alignment": 32}
    for _ in range(n_kv):
        key, off = _read_gguf_str(buf, off)
        (vtype,) = struct.unpack_from("<I", buf, off); off += 4
        if key in ("general.name", "general.architecture") and vtype == 8:
            val, off = _read_gguf_str(buf, off); meta[key] = val
        elif key == "general.alignment" and vtype == 4:
            (val,) = struct.unpack_from("<I", buf, off); off += 4; meta["alignment"] = val
        else:
            off = _skip_gguf_value(buf, off, vtype)
    infos = []
    for _ in range(n_tensors):
        name, off = _read_gguf_str(buf, off)
        (nd,) = struct.unpack_from("<I", buf, off); off += 4
        dims = list(struct.unpack_from("<" + "Q" * nd, buf, off)); off += 8 * nd
        (gtype,) = struct.unpack_from("<I", buf, off); off += 4
        (toff,) = struct.unpack_from("<Q", buf, off); off += 8
        infos.append((name, dims, gtype, toff))
    align = meta["alignment"]
    data_start = (off + align - 1) // align * align
    sd = {}
    for name, dims, gtype, toff in infos:
        n = 1
        for d in dims:
            n *= d
        start = data_start + toff
        if gtype in _GGML_DSIZE:                           # F32 / F16
            dsize = _GGML_DSIZE[gtype]
            raw = buf[start:start + n * dsize]
            dt = np.float32 if gtype == 0 else np.float16
            arr = np.frombuffer(raw, dtype=dt).astype(np.float32)
        elif gtype == 2:                                   # Q4_0 (real ggml dequant)
            nblocks = n // 32
            raw = buf[start:start + nblocks * 18]
            arr = _dequant_q4_0(raw, nblocks)
        else:
            raise SystemExit(f"tensor {name} ggml_type={gtype} unhandled")
        # This export wrote dims in numpy (out,in) order, row-major (verified by Gate A
        # vs the npz source) — reshape directly, NO reversal, NO transpose.
        arr = arr.reshape(dims)
        sd[_rev_name(name)] = arr
    return sd, meta

# ── model loading ───────────────────────────────────────────────────────────────

def _cfg() -> ModelConfig:
    return ModelConfig(vocab_size=259, n_layers=8, n_heads=6, d_model=384,
                       d_ffn=1536, max_seq_len=1024, rope_base=10000.0,
                       tie_embeddings=True, rms_eps=1e-5, init_std=0.02)


def load_model(path: str, device: torch.device) -> TokenlessLM:
    p = Path(path)
    cfg = _cfg()
    model = TokenlessLM(cfg)
    if p.suffix == ".safetensors":
        from safetensors.torch import load_file
        sd = load_file(str(p))
        model.load_state_dict(sd, strict=True)
    elif p.suffix == ".npz":
        z = np.load(p)
        sd = {k: torch.from_numpy(np.asarray(z[k], dtype=np.float32)) for k in z.files}
        model.load_state_dict(sd, strict=True)
    elif p.suffix == ".gguf":
        npsd, _ = parse_gguf(p)
        sd = {k: torch.from_numpy(v.copy()) for k, v in npsd.items()}
        model.load_state_dict(sd, strict=True)
    else:
        raise SystemExit(f"unknown checkpoint format: {p.suffix}")
    return model.to(device).eval()

# ── perplexity (benchmark methodology) ───────────────────────────────────────────

@torch.no_grad()
def score_ppl(model: TokenlessLM, val: np.ndarray, device: torch.device,
              seq_len: int = 1024) -> dict:
    n_chunks = (len(val) - 1) // seq_len                  # non-overlap, drop remainder
    total_nll, total_toks = 0.0, 0
    for i in range(n_chunks):
        s = i * seq_len
        chunk = val[s:s + seq_len + 1]
        if len(chunk) < seq_len + 1:
            break
        x = torch.as_tensor(chunk[:-1].astype(np.int64), device=device)[None, :]
        y = torch.as_tensor(chunk[1:].astype(np.int64), device=device)[None, :]
        logits = model(x).float()                         # [1,T,V]
        log_probs = logits - torch.logsumexp(logits, dim=-1, keepdim=True)
        nll = -log_probs.gather(-1, y[..., None]).squeeze(-1).sum()
        total_nll += float(nll)
        total_toks += int(y.numel())
    ppl = math.exp(total_nll / max(1, total_toks))
    return {"ppl": round(ppl, 4), "tokens_scored": total_toks, "chunks": n_chunks,
            "nll_per_tok": round(total_nll / max(1, total_toks), 6)}

# ── generation (coherence demo; identical code for both models) ─────────────────

# The 5 canonical probes (subset of the benchmark's 30) where the OLD model's frozen
# outputs verse-hop / emit markers — the clearest coherence contrast.
PROBES = [
    ("gen_1_1",  "In the beginning God created the heaven and the earth."),
    ("psa_23_1", "The LORD is my shepherd;"),
    ("jhn_3_16", "For God so loved the world, that he gave his only begotten Son,"),
    ("pro_3_5",  "Trust in the LORD with all thine heart;"),
    ("exo_20_1", "And God spake all these words, saying,"),
]


@torch.no_grad()
def generate(model: TokenlessLM, prompt: str, device: torch.device,
             max_new: int = 100, temperature: float = 0.0, top_k: int = 0) -> str:
    seq_len = model.cfg.max_seq_len
    ids = [b + 3 for b in prompt.encode("utf-8")]          # byte+3, no BOS
    out = []
    for _ in range(max_new):
        ctx = ids[-seq_len:]
        x = torch.as_tensor(ctx, dtype=torch.long, device=device)[None, :]
        logits = model(x)[0, -1].float()                   # [V]
        if temperature <= 0.0:
            nxt = int(torch.argmax(logits).item())         # greedy = deterministic MAP
        else:
            logits = logits / temperature
            if top_k > 0:
                v, _ = torch.topk(logits, min(top_k, logits.numel()))
                logits[logits < v[-1]] = float("-inf")
            probs = torch.softmax(logits, dim=-1)
            nxt = int(torch.multinomial(probs, 1).item())
        ids.append(nxt)
        if nxt in (0, 1, 2):                                # PAD/BOS/EOS → stop
            break
        out.append(nxt - 3)
    return bytes(b for b in out if 0 <= b < 256).decode("utf-8", errors="replace")


# ── CLI ──────────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("score"); s.add_argument("--checkpoint", required=True)
    s.add_argument("--val", default="clean"); s.add_argument("--device", default="cpu")

    c = sub.add_parser("compare"); c.add_argument("--old", required=True)
    c.add_argument("--new", required=True); c.add_argument("--val", default="clean")
    c.add_argument("--device", default="cpu")

    a = sub.add_parser("gate-a"); a.add_argument("--gguf", required=True)
    a.add_argument("--npz", required=True)

    b = sub.add_parser("gate-b"); b.add_argument("--checkpoint", required=True)
    b.add_argument("--expect", type=float, default=3.2125)
    b.add_argument("--band", type=float, default=0.15); b.add_argument("--device", default="cpu")

    g = sub.add_parser("gen"); g.add_argument("--old", required=True); g.add_argument("--new", required=True)
    g.add_argument("--device", default="cpu"); g.add_argument("--max-new", type=int, default=100)
    g.add_argument("--temperature", type=float, default=0.0); g.add_argument("--top-k", type=int, default=0)

    args = ap.parse_args()

    if args.cmd == "score":
        dev = torch.device(args.device)
        val, label = load_val(args.val)
        m = load_model(args.checkpoint, dev)
        r = score_ppl(m, val, dev)
        print(f"checkpoint : {args.checkpoint}")
        print(f"val set    : {label}")
        print(f"PERPLEXITY : {r['ppl']}   (tokens={r['tokens_scored']}, chunks={r['chunks']})")

    elif args.cmd == "compare":
        dev = torch.device(args.device)
        val, label = load_val(args.val)
        old = score_ppl(load_model(args.old, dev), val, dev)
        new = score_ppl(load_model(args.new, dev), val, dev)
        delta = round(old["ppl"] - new["ppl"], 4)
        pct = round(100 * delta / old["ppl"], 2)
        print(f"\n══ HEAD-TO-HEAD on {label} (identical tokens, identical scorer) ══")
        print(f"  OLD (benchmark) : {old['ppl']:.4f}   {args.old}")
        print(f"  NEW (clean)     : {new['ppl']:.4f}   {args.new}")
        print(f"  Δ (old-new)     : {delta:+.4f}  ({pct:+.2f}%  {'NEW WINS' if delta>0 else 'OLD WINS'})")
        print(f"  tokens={old['tokens_scored']}  chunks={old['chunks']}")

    elif args.cmd == "gate-a":
        npsd, meta = parse_gguf(Path(args.gguf))
        z = np.load(args.npz)
        bad = 0
        for k in z.files:
            if k not in npsd:
                print(f"  MISSING in gguf: {k}"); bad += 1; continue
            if not np.allclose(npsd[k], np.asarray(z[k], dtype=np.float32), atol=1e-6):
                md = float(np.max(np.abs(npsd[k] - z[k]))); print(f"  MISMATCH {k}  max|Δ|={md:.2e}"); bad += 1
        print(f"\n══ GATE A (loader correctness: gguf-reverse vs npz) ══")
        print(f"  gguf general.name = {meta.get('general.name')}   tensors={len(npsd)}")
        print(f"  result: {'PASS — reverse map exact, all 74 tensors allclose' if bad==0 else f'FAIL — {bad} tensor(s) off'}")
        sys.exit(0 if bad == 0 else 1)

    elif args.cmd == "gate-b":
        dev = torch.device(args.device)
        val, label = load_val("marker")
        r = score_ppl(load_model(args.checkpoint, dev), val, dev)
        lo, hi = args.expect - args.band, args.expect + args.band
        ok = lo <= r["ppl"] <= hi
        print(f"\n══ GATE B (scorer+identity: marker ppl reproduces published) ══")
        print(f"  {args.checkpoint}  on {label}")
        print(f"  ppl={r['ppl']}  (tokens={r['tokens_scored']}, chunks={r['chunks']})")
        print(f"  band=[{lo:.2f},{hi:.2f}] around published {args.expect}")
        print(f"  result: {'PASS — scorer reproduces benchmark methodology; this model ≈ published' if ok else 'OUT OF BAND — different checkpoint or framework drift (see Gate A to rule out loader)'}")
        sys.exit(0 if ok else 1)

    elif args.cmd == "gen":
        dev = torch.device(args.device)
        old = load_model(args.old, dev)
        new = load_model(args.new, dev)
        mode = "greedy" if args.temperature <= 0 else f"temp={args.temperature},top_k={args.top_k}"
        print(f"\n══ GENERATION side-by-side ({mode}, identical code) ══")
        print(f"  OLD: {args.old}\n  NEW: {args.new}\n")
        for pid, prompt in PROBES:
            go = generate(old, prompt, dev, args.max_new, args.temperature, args.top_k)
            gn = generate(new, prompt, dev, args.max_new, args.temperature, args.top_k)
            print(f"── {pid}  PROMPT: {prompt!r}")
            print(f"   OLD →{go!r}")
            print(f"   NEW →{gn!r}\n")


if __name__ == "__main__":
    main()
