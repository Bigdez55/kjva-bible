#!/usr/bin/env python3
"""
serve_raw_model.py — HTTP inference server for the current Tokenless MLX export.

Pure stdlib http.server + MLX. Exposes:

  GET  /healthz                 liveness + model info
  POST /generate                {"prompt": str, "max_tokens": int,
                                 "temperature": float, "top_k": int}
                                returns JSON {"text": "...", "prompt_tokens": N, ...}
  POST /stream                  same body, returns SSE stream of tokens
  POST /v1/completions          OpenAI-compatible (subset) for drop-in UI use

CORS is open to any origin so a browser UI can call it during testing.

Usage:
  source "training/.venv/bin/activate"
  python training/scripts/serve_raw_model.py \
      --export "$TOKENLESS_HOME/exports/bpe_v1_20m" \
      --port 8088

Test:
  curl -s http://localhost:8088/healthz | jq
  curl -s -X POST http://localhost:8088/generate \
       -H 'content-type: application/json' \
       -d '{"prompt":"Hello, world.","max_tokens":80}'
"""
from __future__ import annotations

import argparse
import codecs
import json
import os
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock

import mlx.core as mx
from mlx.utils import tree_unflatten

# NOTE: `sentencepiece` is imported LAZILY inside the spm branch of the service
# (see TokenlessRawService.__init__). Byte-level exports never produce a
# `tokenizer.model`, and a byte-only serving box may not have sentencepiece
# installed at all — a top-level import would crash that box before the byte
# branch ever runs. (Mirrors eval_clean_ppl.py's per-branch lazy loaders.)

sys.path.insert(0, str(Path(__file__).parent))
from model import ModelConfig, TokenlessLM  # noqa


# ---------------------------------------------------------------------------
# Model wrapper
# ---------------------------------------------------------------------------

class TokenlessRawService:
    def __init__(self, export_dir: Path):
        self.export_dir = export_dir
        cfg_path  = export_dir / "model_config.json"
        w_path    = export_dir / "weights.safetensors"
        tok_path  = export_dir / "tokenizer.model"
        vocab_path = export_dir / "byte_vocab.json"
        man_path  = export_dir / "manifest.json"

        cfg_data = json.loads(cfg_path.read_text())
        self.cfg = ModelConfig(**cfg_data)
        self.model = TokenlessLM(self.cfg)
        weights = mx.load(str(w_path))
        self.model.update(tree_unflatten(list(weights.items())))
        self.manifest = json.loads(man_path.read_text()) if man_path.exists() else {}
        self.model_id = self.manifest.get("model_id") or export_dir.name

        # ── tokenization mode (auto-detect: byte vs spm/BPE) ───────────────────
        # Byte-level exports (safetensors_to_gguf.py writes tokenizer.model ==
        # "byte_level" / tokenization "utf8_byte") emit a `byte_vocab.json` and
        # NEVER a SentencePiece `tokenizer.model`. Key the mode on its presence;
        # also honor an explicit `tokenization == "utf8_byte"` in model_config.
        cfg_tok = str(cfg_data.get("tokenization", "")).lower()
        self.byte_mode = vocab_path.exists() or cfg_tok in ("utf8_byte", "byte_level")

        if self.byte_mode:
            # byte+3 contract (mirrors pt/eval_clean_ppl.py): token = byte + offset,
            # reserved PAD/BOS/EOS at the low ids. Pull the actual offsets from
            # byte_vocab.json when present, else fall back to the canonical defaults.
            vocab = json.loads(vocab_path.read_text()) if vocab_path.exists() else {}
            self.byte_offset = int(vocab.get("byte_offset", 3))
            self.pad_id = int(vocab.get("pad_id", 0))
            self.bos_id = int(vocab.get("bos_id", 1))
            self.eos_id = int(vocab.get("eos_id", 2))
            self._stop_ids = {self.pad_id, self.bos_id, self.eos_id}
            self.tokenizer = None  # no SentencePiece in byte mode
            self.tokenizer_kind = vocab.get("kind", "utf8_byte")
        else:
            # Legacy spm/BPE export — lazy-import sentencepiece only on this path.
            import sentencepiece as spm  # noqa: PLC0415
            if not tok_path.exists():
                raise FileNotFoundError(
                    f"spm/BPE export expected a SentencePiece tokenizer.model at "
                    f"{tok_path}, and no byte_vocab.json was found either. This "
                    f"export is neither a valid byte nor a valid BPE bundle.")
            self.tokenizer = spm.SentencePieceProcessor(model_file=str(tok_path))
            self.tokenizer_kind = "spm"

        # MLX is not inherently thread-safe for shared mutable state;
        # serialize inference with a lock.
        self._lock = Lock()

    def info(self) -> dict:
        return {
            "status": "ok",
            "service": "Tokenless raw model server",
            "model": self.model_id,
            "tokenization": self.tokenizer_kind,
            "n_parameters": self.manifest.get("n_parameters"),
            "architecture": self.cfg.to_dict(),
            "weights_sha256": self.manifest.get("weights_sha256", "")[:16],
            "attestation": self.manifest.get("tokenless_attestation", ""),
        }

    def encode_prompt(self, prompt: str) -> list[int]:
        """Mode-aware prompt → token-id encoding.

        spm/BPE : [bos_id] + tokenizer.encode(prompt)   (BOS prepended)
        byte    : [b + byte_offset for b in prompt.encode("utf-8")]  (NO BOS,
                  matching pt/eval_clean_ppl.py's byte+3 raw-stream contract)
        """
        if self.byte_mode:
            return [b + self.byte_offset for b in prompt.encode("utf-8")]
        return [self.tokenizer.bos_id()] + self.tokenizer.encode(prompt)

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
        """Yields (token_id, delta_text) per step. Dispatches on tokenization
        mode (byte vs spm). Delta is the NEWLY decoded text since the last step.
        """
        if self.byte_mode:
            yield from self._generate_byte(prompt, max_tokens, temperature, top_k)
        else:
            yield from self._generate_spm(prompt, max_tokens, temperature, top_k)

    def _generate_spm(self, prompt: str, max_tokens: int,
                      temperature: float, top_k: int):
        """Legacy spm/BPE path (unchanged contract: BOS prepended, stop on EOS,
        cumulative decode so byte-fallback pieces resolve into UTF-8)."""
        with self._lock:
            ids = self.encode_prompt(prompt)
            tokens = mx.array(ids, dtype=mx.int32)[None, :]
            out_ids: list[int] = []
            decoded_so_far = ""
            for _ in range(max_tokens):
                T = tokens.shape[1]
                if T > self.cfg.max_seq_len:
                    tokens = tokens[:, -self.cfg.max_seq_len:]
                logits = self.model(tokens)[0, -1, :]
                mx.eval(logits)
                nid = self._sample(logits, temperature, top_k)
                if nid == self.tokenizer.eos_id():
                    break
                out_ids.append(nid)
                tokens = mx.concatenate([tokens, mx.array([[nid]])], axis=1)
                # Decode the running output so byte-fallback sequences (Greek,
                # Hebrew, newline etc.) resolve correctly into UTF-8.
                full = self.tokenizer.decode(out_ids)
                delta = full[len(decoded_so_far):]
                decoded_so_far = full
                if delta:
                    yield nid, delta

    def _generate_byte(self, prompt: str, max_tokens: int,
                       temperature: float, top_k: int):
        """Byte-level path — mirrors pt/eval_clean_ppl.py's `generate`:
          • encode  : token = byte + byte_offset, NO BOS inserted
          • sample  : reuse self._sample (greedy when temperature<=0)
          • stop    : any reserved id (PAD/BOS/EOS) ends the stream
          • decode  : nid - byte_offset back to a raw byte, fed through an
                      INCREMENTAL UTF-8 decoder so multi-byte characters that
                      span several steps are buffered and emitted cleanly
                      (avoids the transient U+FFFD a cumulative slice would show).
        """
        with self._lock:
            ids = self.encode_prompt(prompt)
            if not ids:
                # Empty prompt → empty context. Seed a BOS purely so the forward
                # pass has T>=1 (avoids indexing [-1] on an empty time axis).
                # It is context-only and is never emitted.
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
                if nid in self._stop_ids:          # PAD / BOS / EOS → stop
                    break
                tokens = mx.concatenate([tokens, mx.array([[nid]])], axis=1)
                byte_val = nid - self.byte_offset
                if not (0 <= byte_val < 256):       # out-of-range guard
                    continue
                delta = decoder.decode(bytes([byte_val]))
                if delta:
                    yield nid, delta


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    service: "TokenlessRawService" = None  # set at server start

    # Silence the default stderr access log
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
        raw = self.rfile.read(n)
        try:
            return json.loads(raw)
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
                payload = json.dumps({"token": piece})
                self.wfile.write(f"data: {payload}\n\n".encode("utf-8"))
                self.wfile.flush()
            done = json.dumps({
                "done": True,
                "text": "".join(pieces),
                "elapsed_s": round(time.time() - t_start, 3),
            })
            self.wfile.write(f"data: {done}\n\n".encode("utf-8"))
            self.wfile.flush()
        else:
            t_start = time.time()
            pieces = []
            for _nid, piece in self.service.generate(prompt, max_tokens, temperature, top_k):
                pieces.append(piece)
            text = "".join(pieces)
            resp = {
                "prompt": prompt,
                "text": text,
                "full": prompt + text,
                "generated_tokens": len(pieces),
                "elapsed_s": round(time.time() - t_start, 3),
                "temperature": temperature,
                "top_k": top_k,
            }
            body_out = json.dumps(resp).encode("utf-8")
            self.send_response(200)
            self._cors()
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(body_out)))
            self.end_headers()
            self.wfile.write(body_out)

    def _do_openai_completions(self):
        """Minimal OpenAI /v1/completions compat: prompt -> choices[0].text."""
        body = self._read_json()
        prompt = body.get("prompt", "")
        if isinstance(prompt, list):
            prompt = prompt[0] if prompt else ""
        max_tokens  = int(body.get("max_tokens", 120))
        temperature = float(body.get("temperature", 0.8))
        top_k       = int(body.get("top_k", 40))

        # Mode-aware prompt length (byte: no BOS; spm: BOS included) — computed
        # before generation so it's available for the usage block below.
        prompt_token_count = len(self.service.encode_prompt(prompt))

        t_start = time.time()
        pieces = []
        for _nid, piece in self.service.generate(prompt, max_tokens, temperature, top_k):
            pieces.append(piece)
        text = "".join(pieces)

        resp = {
            "id": f"tokenless-{int(time.time())}",
            "object": "text_completion",
            "created": int(time.time()),
            "model": self.service.model_id,
            "choices": [{
                "text": text,
                "index": 0,
                "logprobs": None,
                "finish_reason": "length",
            }],
            "usage": {
                # encode_prompt already accounts for the (spm-only) BOS, so this
                # is the true context length in both byte and spm modes.
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


def main():
    parser = argparse.ArgumentParser()
    script_dir = Path(__file__).resolve().parent
    training_dir = script_dir.parent
    default_home = Path(os.environ.get("TOKENLESS_HOME", str(training_dir)))
    default_export = os.environ.get("TOKENLESS_EXPORT_DIR", str(default_home / "exports/bpe_v1_20m"))
    parser.add_argument("--export", default=default_export,
                        help="Export directory (contains weights.safetensors etc.)")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8088)
    args = parser.parse_args()

    export_dir = Path(args.export)
    if not export_dir.exists():
        print(f"ERROR: export dir not found: {export_dir}", file=sys.stderr)
        sys.exit(1)

    print(f"Loading Tokenless model export from: {export_dir}", file=sys.stderr)
    svc = TokenlessRawService(export_dir)
    Handler.service = svc
    print(f"  params: {svc.manifest.get('n_parameters', '?')}", file=sys.stderr)
    print(f"  weights sha256[:16]: {svc.manifest.get('weights_sha256','')[:16]}", file=sys.stderr)

    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Serving on http://{args.host}:{args.port}", file=sys.stderr)
    print("Endpoints:", file=sys.stderr)
    print("  GET  /healthz", file=sys.stderr)
    print("  POST /generate         {prompt, max_tokens, temperature, top_k}", file=sys.stderr)
    print("  POST /stream           SSE token stream", file=sys.stderr)
    print("  POST /v1/completions   OpenAI-compatible subset", file=sys.stderr)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.", file=sys.stderr)
        srv.shutdown()


if __name__ == "__main__":
    main()
