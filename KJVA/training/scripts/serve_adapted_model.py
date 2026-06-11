#!/usr/bin/env python3
"""
serve_adapted_model.py — MLX inference server with full OMNI-PEFT adapter injection.

This is the "hot-swap" deployment mode from the OMNI-PEFT design.
All 4 operators (LoRA + IA3 + BitFit + PrefixTuning) are injected at startup
via inject_into() — no partial baking, no BPB regression, full composite active.

The XMIND C engine only supports LoRA-only adapters via safetensors.
This MLX path supports the full composite without any baking compromise.

Usage:
  source "training/.venv/bin/activate"
  python3 training/scripts/serve_adapted_model.py \\
      --weights  training/runs/byte_clean_v2/ckpt_step_003000.safetensors \\
      --config   training/runs/byte_clean_v2/model_config.json \\
      --adapter  training/runs/omni_scribe_pareto/omni_adapter_weights.npz \\
      --vocab    training/runs/byte_clean_v2/byte_vocab.json \\
      --port 8089

  # Or using defaults (auto-resolved from training/ tree):
  python3 training/scripts/serve_adapted_model.py --port 8089

Endpoints (same contract as serve_raw_model.py):
  GET  /healthz                 liveness + model + adapter info
  POST /generate                {"prompt": str, "max_tokens": int, "temperature": float, "top_k": int}
  POST /stream                  same body, SSE stream
  POST /v1/completions          OpenAI-compatible subset
"""
from __future__ import annotations

import argparse
import codecs
import json
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock

import mlx.core as mx
import mlx.nn as nn
import numpy as np
from mlx.utils import tree_unflatten

sys.path.insert(0, str(Path(__file__).parent))
from model import ModelConfig, TokenlessLM

sys.path.insert(0, str(Path(__file__).parent.parent))


# ---------------------------------------------------------------------------
# Adapter reconstruction from NPZ
# ---------------------------------------------------------------------------

def _load_composite_from_npz(npz_path: str, base_model: TokenlessLM):
    """
    Reconstruct an OmniPEFTCompositeAdapter from a saved NPZ file and
    inject it into base_model.

    The NPZ stores:
      op_layer{N}_{slot}.weight_op.A   — LoRA A  (rank, in_features)
      op_layer{N}_{slot}.weight_op.B   — LoRA B  (out_features, rank)
      op_layer{N}_{slot}.ia3_scale     — IA3 scale  (out_features,)
      op_layer{N}_{slot}.bitfit_bias   — BitFit bias (out_features,)
      prefix_tuning.prefix_key         — (n_layers, n_prefix, d_kv)
      prefix_tuning.prefix_val         — (n_layers, n_prefix, d_kv)

    Returns: (composite, rollback_dict, stats)
    """
    from peft.omni_composite import OmniPEFTCompositeAdapter, _OmniPatched
    from peft.low_rank.lora import LoRALinear
    from peft.prompt.prefix_tuning import PrefixTuningLayer

    npz = np.load(npz_path)
    all_keys = set(npz.files)

    # --- Discover layer slots ---
    slots: dict[str, dict] = {}  # "layer{N}.attn.{proj}" -> {"A", "B", "ia3", "bias"}
    for k in all_keys:
        if not k.startswith("op_layer"):
            continue
        # k: "op_layer2_attn_q.weight_op.A"
        dot_pos = k.index(".")
        prefix = k[:dot_pos]       # "op_layer2_attn_q"
        component = k[dot_pos + 1:]  # "weight_op.A"

        # Parse prefix -> layer_idx, module_name
        rest = prefix[len("op_layer"):]  # "2_attn_q"
        underscore = rest.index("_")
        layer_idx = int(rest[:underscore])
        slot_name = rest[underscore + 1:]  # "attn_q"
        module_name = slot_name.replace("_", ".", 1)  # "attn.q"

        canon_key = f"layer{layer_idx}.{module_name}"
        if canon_key not in slots:
            slots[canon_key] = {}

        if component == "weight_op.A":
            slots[canon_key]["A"] = npz[k]
        elif component == "weight_op.B":
            slots[canon_key]["B"] = npz[k]
        elif component == "ia3_scale":
            slots[canon_key]["ia3"] = npz[k]
        elif component == "bitfit_bias":
            slots[canon_key]["bias"] = npz[k]

    # --- Build composite ---
    composite = OmniPEFTCompositeAdapter()
    stats = {"lora": 0, "ia3": 0, "bitfit": 0, "prefix": False, "skipped": 0}

    for canon_key, comps in slots.items():
        # Resolve base linear from model
        parts = canon_key.split(".", 1)  # ["layer2", "attn.q"]
        try:
            layer_idx = int(parts[0][len("layer"):])
        except (ValueError, IndexError):
            stats["skipped"] += 1
            continue
        module_path = parts[1]  # "attn.q"

        block = base_model.blocks[layer_idx]
        obj = block
        for p in module_path.split("."):
            obj = getattr(obj, p, None)
            if obj is None:
                break
        if obj is None or not hasattr(obj, "weight"):
            stats["skipped"] += 1
            continue

        out_f, in_f = obj.weight.shape

        # Build LoRALinear if A and B are present
        weight_op = None
        if "A" in comps and "B" in comps:
            A = mx.array(comps["A"])  # (rank, in_features)
            B = mx.array(comps["B"])  # (out_features, rank)
            rank = A.shape[0]
            lora = LoRALinear(in_f, out_f, rank=rank, alpha=float(rank * 2))
            lora.A = A
            lora.B = B
            weight_op = lora
            stats["lora"] += 1

        # IA3 activation scale
        ia3_scale = None
        if "ia3" in comps:
            ia3_scale = mx.array(comps["ia3"])
            stats["ia3"] += 1

        # BitFit bias
        bitfit_bias = None
        if "bias" in comps:
            bitfit_bias = mx.array(comps["bias"])
            stats["bitfit"] += 1

        patched = _OmniPatched(obj, weight_op, ia3_scale, bitfit_bias)

        # Register using flat attr name (no dots — MLX path separator)
        slot_flat = module_path.replace(".", "_")  # "attn_q"
        attr_name = f"op_layer{layer_idx}_{slot_flat}"
        setattr(composite, attr_name, patched)
        composite._key_to_attr[canon_key] = attr_name
        composite._operator_count += 1

    # --- Prefix tuning ---
    pk_key = "prefix_tuning.prefix_key"
    pv_key = "prefix_tuning.prefix_val"
    if pk_key in all_keys and pv_key in all_keys:
        pk = npz[pk_key]  # (n_layers, n_prefix, d_kv)
        pv = npz[pv_key]
        n_layers, n_prefix, d_kv = pk.shape
        cfg = base_model.cfg
        n_heads = cfg.n_heads
        head_dim = cfg.head_dim

        prefix_layer = PrefixTuningLayer(
            n_prefix=n_prefix,
            n_heads=n_heads,
            head_dim=head_dim,
            n_layers=n_layers,
        )
        prefix_layer.prefix_key = mx.array(pk)
        prefix_layer.prefix_val = mx.array(pv)
        composite.prefix_tuning = prefix_layer
        stats["prefix"] = True

    composite._genome_methods = sorted(set(
        (["lora"] if stats["lora"] > 0 else []) +
        (["ia3"] if stats["ia3"] > 0 else []) +
        (["bitfit"] if stats["bitfit"] > 0 else []) +
        (["prefix_tuning"] if stats["prefix"] else [])
    ))

    # Inject all operators into the base model
    rollback = composite.inject_into(base_model)
    return composite, rollback, stats


# ---------------------------------------------------------------------------
# Adapted model service
# ---------------------------------------------------------------------------

class AdaptedModelService:
    def __init__(
        self,
        weights_path: str,
        config_path: str,
        vocab_path: str,
        adapter_path: str,
    ):
        print(f"[serve_adapted] Loading base weights: {weights_path}", file=sys.stderr)
        cfg_data = json.loads(Path(config_path).read_text())
        self.cfg = ModelConfig(**cfg_data)
        self.model = TokenlessLM(self.cfg)

        weights = mx.load(weights_path)
        self.model.update(tree_unflatten(list(weights.items())))
        mx.eval(self.model.parameters())

        # Byte-level vocab
        vocab_data = json.loads(Path(vocab_path).read_text())
        self.byte_offset = int(vocab_data.get("byte_offset", 3))
        self.bos_id = int(vocab_data.get("bos_id", 1))
        self.eos_id = int(vocab_data.get("eos_id", 2))
        self.pad_id = int(vocab_data.get("pad_id", 0))
        self._stop_ids = {self.pad_id, self.bos_id, self.eos_id}

        # Inject adapter
        print(f"[serve_adapted] Injecting adapter: {adapter_path}", file=sys.stderr)
        self._composite, self._rollback, self._adapter_stats = \
            _load_composite_from_npz(adapter_path, self.model)
        mx.eval(self.model.parameters())

        self.weights_sha = _sha256_file(weights_path)[:16]
        self.adapter_sha = _sha256_file(adapter_path)[:16]
        self.adapter_path = adapter_path
        self._lock = Lock()

        print(f"[serve_adapted] Ready — operators: {self._composite._genome_methods}", file=sys.stderr)
        print(f"[serve_adapted] Slots: {self._composite._operator_count}, "
              f"prefix: {self._adapter_stats['prefix']}", file=sys.stderr)

    def info(self) -> dict:
        return {
            "status": "ok",
            "service": "OMNI-PEFT adapted model server (MLX hot-swap)",
            "base_sha256": self.weights_sha,
            "adapter_sha256": self.adapter_sha,
            "adapter_operators": self._composite._genome_methods,
            "operator_count": self._composite._operator_count,
            "adapter_stats": {k: int(v) if isinstance(v, (int, np.integer)) else v
                              for k, v in self._adapter_stats.items()},
            "architecture": self.cfg.to_dict(),
        }

    def encode_prompt(self, prompt: str) -> list[int]:
        return [b + self.byte_offset for b in prompt.encode("utf-8")]

    def _sample(self, logits: mx.array, temperature: float, top_k: int) -> int:
        if temperature <= 0:
            return int(mx.argmax(logits).item())
        scaled = logits / temperature
        if top_k and top_k > 0:
            top_vals = mx.topk(scaled, top_k)
            threshold = mx.min(top_vals)
            scaled = mx.where(
                scaled >= threshold,
                scaled,
                mx.full(scaled.shape, -1e9, dtype=scaled.dtype),
            )
        probs = mx.softmax(scaled, axis=-1)
        return int(mx.random.categorical(mx.log(probs + 1e-9)).item())

    def generate(self, prompt: str, max_tokens: int = 120,
                 temperature: float = 0.8, top_k: int = 40):
        """Yields (token_id, delta_text) per step."""
        with self._lock:
            ids = self.encode_prompt(prompt)
            if not ids:
                ids = [self.bos_id]
            tokens = mx.array(ids, dtype=mx.int32)[None, :]
            decoder = codecs.getincrementaldecoder("utf-8")("replace")

            for _ in range(max_tokens):
                T = tokens.shape[1]
                if T > self.cfg.max_seq_len:
                    tokens = tokens[:, -self.cfg.max_seq_len:]
                logits = self.model(tokens)[0, -1, :]
                mx.eval(logits)
                nid = self._sample(logits, temperature, top_k)
                if nid in self._stop_ids:
                    break
                tokens = mx.concatenate([tokens, mx.array([[nid]])], axis=1)
                byte_val = nid - self.byte_offset
                if not (0 <= byte_val < 256):
                    continue
                delta = decoder.decode(bytes([byte_val]))
                if delta:
                    yield nid, delta


def _sha256_file(path: str) -> str:
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# HTTP handler (same contract as serve_raw_model.py)
# ---------------------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    service: "AdaptedModelService" = None

    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write("[%s] %s\n" % (self.log_date_time_string(), fmt % args))

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "content-type, authorization")

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        if self.path == "/healthz":
            body = json.dumps(self.service.info()).encode("utf-8")
            self.send_response(200)
            self._cors()
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(404)
        self._cors()
        self.end_headers()

    def _read_json(self) -> dict:
        n = int(self.headers.get("content-length", 0) or 0)
        if n <= 0:
            return {}
        try:
            return json.loads(self.rfile.read(n))
        except json.JSONDecodeError:
            return {}

    def do_POST(self):
        if self.path == "/generate":
            return self._do_generate(stream=False)
        if self.path == "/stream":
            return self._do_generate(stream=True)
        if self.path == "/v1/completions":
            return self._do_openai_completions()
        self.send_response(404)
        self._cors()
        self.end_headers()

    def _do_generate(self, stream: bool):
        body = self._read_json()
        prompt = body.get("prompt", "")
        if not isinstance(prompt, str):
            self._err(400, "prompt must be a string")
            return
        max_tokens  = int(body.get("max_tokens", 120))
        temperature = float(body.get("temperature", 0.8))
        top_k       = int(body.get("top_k", 40))

        if stream:
            self.send_response(200)
            self._cors()
            self.send_header("content-type", "text/event-stream")
            self.send_header("cache-control", "no-cache")
            self.send_header("x-accel-buffering", "no")
            self.end_headers()
            t_start = time.time()
            pieces = []
            for _nid, piece in self.service.generate(prompt, max_tokens, temperature, top_k):
                pieces.append(piece)
                self.wfile.write(
                    f"data: {json.dumps({'token': piece})}\n\n".encode("utf-8"))
                self.wfile.flush()
            done = json.dumps({"done": True, "text": "".join(pieces),
                               "elapsed_s": round(time.time() - t_start, 3)})
            self.wfile.write(f"data: {done}\n\n".encode("utf-8"))
            self.wfile.flush()
        else:
            t_start = time.time()
            pieces = [p for _, p in
                      self.service.generate(prompt, max_tokens, temperature, top_k)]
            resp = {
                "prompt": prompt,
                "text": "".join(pieces),
                "full": prompt + "".join(pieces),
                "generated_tokens": len(pieces),
                "elapsed_s": round(time.time() - t_start, 3),
                "temperature": temperature,
                "top_k": top_k,
            }
            b = json.dumps(resp).encode("utf-8")
            self.send_response(200)
            self._cors()
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)

    def _do_openai_completions(self):
        body = self._read_json()
        prompt = body.get("prompt", "")
        if isinstance(prompt, list):
            prompt = prompt[0] if prompt else ""
        max_tokens  = int(body.get("max_tokens", 120))
        temperature = float(body.get("temperature", 0.8))
        top_k       = int(body.get("top_k", 40))

        prompt_token_count = len(self.service.encode_prompt(prompt))
        t_start = time.time()
        pieces = [p for _, p in
                  self.service.generate(prompt, max_tokens, temperature, top_k)]
        text = "".join(pieces)

        resp = {
            "id": f"omni-adapted-{int(time.time())}",
            "object": "text_completion",
            "created": int(time.time()),
            "model": "kjva-byte-omni-adapted",
            "choices": [{"text": text, "index": 0,
                         "logprobs": None, "finish_reason": "length"}],
            "usage": {
                "prompt_tokens": prompt_token_count,
                "completion_tokens": len(pieces),
                "total_tokens": prompt_token_count + len(pieces),
            },
        }
        b = json.dumps(resp).encode("utf-8")
        self.send_response(200)
        self._cors()
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def _err(self, code: int, msg: str):
        body = json.dumps({"error": msg}).encode("utf-8")
        self.send_response(code)
        self._cors()
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    script_dir = Path(__file__).resolve().parent
    training_dir = script_dir.parent

    defaults = {
        "weights": str(training_dir / "runs/byte_clean_v2/ckpt_step_003000.safetensors"),
        "config":  str(training_dir / "runs/byte_clean_v2/model_config.json"),
        "vocab":   str(training_dir / "runs/byte_clean_v2/byte_vocab.json"),
        "adapter": str(training_dir / "runs/omni_scribe_pareto/omni_adapter_weights.npz"),
    }

    parser = argparse.ArgumentParser(
        description="Serve KJVA byte-level model with full OMNI-PEFT adapter (MLX hot-swap)")
    parser.add_argument("--weights",  default=defaults["weights"])
    parser.add_argument("--config",   default=defaults["config"])
    parser.add_argument("--vocab",    default=defaults["vocab"])
    parser.add_argument("--adapter",  default=defaults["adapter"])
    parser.add_argument("--host",     default="127.0.0.1")
    parser.add_argument("--port",     type=int, default=8089)
    args = parser.parse_args()

    for label, path in [("weights", args.weights), ("config", args.config),
                        ("vocab", args.vocab), ("adapter", args.adapter)]:
        if not Path(path).exists():
            print(f"ERROR: {label} not found: {path}", file=sys.stderr)
            sys.exit(1)

    svc = AdaptedModelService(args.weights, args.config, args.vocab, args.adapter)
    Handler.service = svc

    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"[serve_adapted] Listening on http://{args.host}:{args.port}", file=sys.stderr)
    print("[serve_adapted] Endpoints:", file=sys.stderr)
    print("  GET  /healthz", file=sys.stderr)
    print("  POST /generate         {prompt, max_tokens, temperature, top_k}", file=sys.stderr)
    print("  POST /stream           SSE token stream", file=sys.stderr)
    print("  POST /v1/completions   OpenAI-compatible subset", file=sys.stderr)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n[serve_adapted] Shutting down.", file=sys.stderr)
        srv.shutdown()


if __name__ == "__main__":
    main()
