# ADR 0001: MLX as inference engine

## Status

Accepted (retroactive — captures the existing decision visible in backend/inference.py and backend/model.py)

## Context

KJVA is an 18M-parameter byte-level transformer. The model was trained on, and is intended to run on, Apple Silicon developer hardware (unified memory, no separate GPU VRAM). The author's primary workstation is a Mac. A runtime had to be picked for serving the model from FastAPI without dragging in PyTorch+CUDA or TensorFlow.

## Decision

Use Apple's MLX (`mlx>=0.16.0`) as the model runtime. The model definition in `backend/model.py` is a `TokenlessLM` MLX module; the inference loop in `backend/inference.py` uses MLX arrays end-to-end (sampling, top-p filtering, KV-cache stays on the unified-memory device).

## Options considered

1. **MLX** — Apple-native, zero-copy on Apple Silicon, small dep footprint.
2. **PyTorch (MPS backend)** — Wider ecosystem, but heavy dep, MPS still has gaps on some ops.
3. **GGML / llama.cpp** — Excellent CPU inference, but requires re-quantizing weights and using a custom .gguf format; loses byte-level tokenizer tooling.
4. **ONNX Runtime** — Cross-platform, but conversion of a custom byte-level transformer is awkward and the Apple Silicon path is not first-class.

## Why this decision wins

MLX gives the smallest runtime footprint on the actual deployment hardware (Apple Silicon dev box), avoids a 1+ GB PyTorch install, and trains+infers in the same framework — no model conversion step between training and serving.

## Tradeoffs

- **Benefit:** Smallest dep tree of any candidate. Zero copy between Python and Metal.
- **Benefit:** Same framework for training (off-tree, in Tokenless-Models) and inference.
- **Cost:** Apple Silicon only. Containers on linux/amd64 cannot run the AI fallback path. Retrieval-only mode (ADR-0003) is the mitigation.
- **Risk:** MLX is young; API churn is possible. Pinned via `mlx>=0.16.0` and verified against current backend.
- **Reversibility:** Medium. Model weights would need to be re-exported to a portable format (safetensors → torch state_dict → load in alternate runtime) — possible but a multi-day effort.

## Affected components

- `backend/model.py` — `TokenlessLM` MLX module
- `backend/inference.py` — `KJVAInference` runtime, sampling, completion API
- `KJVA/training/weights.safetensors` — model weights format

## Rollback path

Re-export weights to PyTorch state_dict, replace `backend/model.py` with an `nn.Module`, and swap `backend/inference.py` for a PyTorch-MPS or CPU inference loop. Retrieval (ADR-0003) is unaffected and would continue working throughout the swap.
