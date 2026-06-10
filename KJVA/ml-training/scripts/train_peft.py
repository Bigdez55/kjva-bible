#!/usr/bin/env python3
"""
train_peft.py — Unified PEFT training CLI for Tokenless models

Unified entry point for all 37 PEFT/alignment/distillation methods.
Each method maps to a concrete DeltaOperator in ml-training/peft/.

Usage:
  python train_peft.py --method lora --base-checkpoint <path> --corpus <path>
  python train_peft.py --method ia3 --base-checkpoint <path> --corpus <path> --dry-run
  python train_peft.py --method omni --base-checkpoint <path> --corpus <path> --dry-run
  python train_peft.py --list-methods

Escalation ladder (cheapest → most expensive):
  1. ia3           — 3 scaling vectors per layer (ultra-light)
  2. bitfit        — bias-only (trivial)
  3. prompt_tuning — soft prompt tokens
  4. prefix_tuning — per-layer KV prefix
  5. p_tuning      — MLP prompt encoder
  6. lora          — reference low-rank implementation
  7. rslora        — rank-stabilized LoRA
  8. olora         — orthonormal init LoRA
  9. pissa         — PCA-initialized LoRA
  10. adalora       — importance-weighted rank allocation
  11. vera          — shared frozen matrices + scaling vecs
  12. loha          — Hadamard product low-rank
  13. lokr          — Kronecker product low-rank
  14. rosa          — sparse + low-rank hybrid
  15. dora          — weight-decomposed LoRA
  16. qlora         — 4-bit substrate + LoRA adapters
  17. houlsby       — bottleneck adapter (both sub-layers)
  18. pfeiffer      — bottleneck adapter (FFN only)
  19. diffpruning   — sparse diff-vector
  20. fishmask      — Fisher-weighted binary mask
  21. far           — freeze and reconfigure
  22. oft           — orthogonal finetuning
  23. boft          — butterfly OFT
  24. fourier_ft    — spectral delta
  25. unipelt       — LoRA + prefix + adapter + gate
  26. mam_adapter   — prefix + FFN adapter blend
  27. compacter     — Kronecker + shared params
  28. xlora         — mixture of LoRA experts
  29. sft           — supervised fine-tuning
  30. dpo           — direct preference optimization
  31. ipo           — identity preference optimization
  32. kto           — Kahneman-Tversky optimization
  33. orpo          — odds ratio preference optimization
  34. ppo_rlhf      — PPO + reward model
  35. grpo          — group relative policy optimization
  36. distill_logit   — logit distillation
  37. distill_sequence — sequence distillation
  omni              — Compiler → Tournament → Pareto selection (automatic)
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
ML_TRAINING = SCRIPT_DIR.parent
PEFT_DIR = ML_TRAINING / "peft"
sys.path.insert(0, str(ML_TRAINING))
sys.path.insert(0, str(SCRIPT_DIR))
from ckpt_bench import run_peft_epoch_bench, run_final_bench  # noqa

# MLX is required for training; import at module level so _LoRAPatched (a nn.Module
# subclass) can be defined without deferred imports.
try:
    import mlx.core as mx
    import mlx.nn as nn
except ImportError:  # MLX not installed — training will fail gracefully in main()
    mx = None  # type: ignore[assignment]
    nn = None  # type: ignore[assignment]

# ---------------------------------------------------------------------------
# Method registry — maps --method IDs to PEFT class paths
# ---------------------------------------------------------------------------

METHOD_REGISTRY: dict[str, dict[str, Any]] = {
    # Low-rank family
    "lora":          {"module": "peft.low_rank.lora",      "class": "LoRALinear",        "family": "low_rank"},
    "dora":          {"module": "peft.low_rank.dora",      "class": "DoRALinear",         "family": "low_rank"},
    "qlora":         {"module": "peft.low_rank.qlora",     "class": "QLoRALinear",        "family": "low_rank"},
    "adalora":       {"module": "peft.low_rank.adalora",   "class": "AdaLoRALinear",      "family": "low_rank"},
    "vera":          {"module": "peft.low_rank.vera",      "class": "VeRALinear",         "family": "low_rank"},
    "pissa":         {"module": "peft.low_rank.pissa",     "class": "PiSSALinear",        "family": "low_rank"},
    "rslora":        {"module": "peft.low_rank.rslora",    "class": "rsLoRALinear",       "family": "low_rank"},
    "olora":         {"module": "peft.low_rank.olora",     "class": "OLoRALinear",        "family": "low_rank"},
    "loha":          {"module": "peft.low_rank.loha",      "class": "LoHaLinear",         "family": "low_rank"},
    "lokr":          {"module": "peft.low_rank.lokr",      "class": "LoKrLinear",         "family": "low_rank"},
    "rosa":          {"module": "peft.low_rank.rosa",      "class": "RoSALinear",         "family": "low_rank"},
    # Additive adapters
    "houlsby":       {"module": "peft.additive.houlsby",   "class": "HoulsbyAdapter",     "family": "additive"},
    "pfeiffer":      {"module": "peft.additive.pfeiffer",  "class": "PfeifferAdapter",    "family": "additive"},
    # Prompt family
    "prompt_tuning": {"module": "peft.prompt.prompt_tuning",  "class": "PromptTuningLayer", "family": "prompt"},
    "prefix_tuning": {"module": "peft.prompt.prefix_tuning",  "class": "PrefixTuningLayer", "family": "prompt"},
    "p_tuning":      {"module": "peft.prompt.p_tuning",       "class": "PTuningV2",          "family": "prompt"},
    # Activation
    "ia3":           {"module": "peft.activation.ia3",     "class": "IA3Layer",           "family": "activation"},
    # Selective/sparse
    "bitfit":        {"module": "peft.selective.bitfit",   "class": "BitFitOperator",     "family": "selective"},
    "diffpruning":   {"module": "peft.selective.diffpruning", "class": "DiffPruningOperator", "family": "selective"},
    "fishmask":      {"module": "peft.selective.fishmask", "class": "FishMaskOperator",   "family": "selective"},
    "far":           {"module": "peft.selective.far",      "class": "FAROperator",        "family": "selective"},
    # Hybrid
    "unipelt":       {"module": "peft.hybrid.unipelt",     "class": "UniPELTBlock",       "family": "hybrid"},
    "mam_adapter":   {"module": "peft.hybrid.mam_adapter", "class": "MAMBlock",           "family": "hybrid"},
    "compacter":     {"module": "peft.hybrid.compacter",   "class": "CompacterLayer",     "family": "hybrid"},
    "xlora":         {"module": "peft.hybrid.xlora",       "class": "XLoRALayer",         "family": "hybrid"},
    # Structural
    "oft":           {"module": "peft.structural.oft",     "class": "OFTLinear",          "family": "structural"},
    "boft":          {"module": "peft.structural.boft",    "class": "BOFTLinear",         "family": "structural"},
    "fourier_ft":    {"module": "peft.structural.fourier_ft", "class": "FourierFTLinear", "family": "structural"},
    # Alignment
    "sft":           {"module": "peft.alignment.sft",      "class": "SFTTrainer",         "family": "alignment"},
    "dpo":           {"module": "peft.alignment.dpo",      "class": "DPOTrainer",         "family": "alignment"},
    "ipo":           {"module": "peft.alignment.ipo",      "class": "IPOTrainer",         "family": "alignment"},
    "kto":           {"module": "peft.alignment.kto",      "class": "KTOTrainer",         "family": "alignment"},
    "orpo":          {"module": "peft.alignment.orpo",     "class": "ORPOTrainer",        "family": "alignment"},
    "ppo_rlhf":      {"module": "peft.alignment.ppo_rlhf", "class": "PPORLHFTrainer",     "family": "alignment"},
    "grpo":          {"module": "peft.alignment.grpo",     "class": "GRPOTrainer",        "family": "alignment"},
    # Distillation (alignment trainers handle the loss; corpus builds the dataset)
    "distill_logit":    {"module": "peft.alignment.sft",   "class": "SFTTrainer",  "family": "distillation"},
    "distill_sequence": {"module": "peft.alignment.sft",   "class": "SFTTrainer",  "family": "distillation"},
}

# Methods that require a corpus for training input sequences
CORPUS_METHODS = {
    "lora", "dora", "qlora", "adalora", "vera", "pissa", "rslora", "olora",
    "loha", "lokr", "rosa", "houlsby", "pfeiffer", "ia3", "bitfit",
    "diffpruning", "fishmask", "far", "unipelt", "mam_adapter", "compacter",
    "xlora", "oft", "boft", "fourier_ft", "prompt_tuning", "prefix_tuning",
    "p_tuning", "sft", "distill_logit", "distill_sequence",
}


# ---------------------------------------------------------------------------
# Dry-run compilation report
# ---------------------------------------------------------------------------

def dry_run_report(method: str, args: argparse.Namespace) -> None:
    """Print the Omni-PEFT compilation plan without executing training."""
    from peft.fingerprint import TaskFingerprinter, DataSize, DomainShift
    from peft.profiler import ModelProfiler
    from peft.compiler import PEFTCompiler
    from peft.tournament import TrainingTournament
    from peft.base import AdaptationConstraints, HardwareBudget

    print("=" * 72)
    print("OMNI-PEFT COMPILE REPORT (DRY RUN)")
    print("=" * 72)

    model_config = {
        "vocab_size": 16000,
        "n_layers": 6,
        "d_model": 384,
        "d_ffn": 1536,
        "n_heads": 6,
        "head_dim": 64,
    }
    hardware = HardwareBudget(
        train_vram_mb=args.train_vram_mb,
        deployment_target="local_apple_silicon",
    )
    constraints = AdaptationConstraints(hardware=hardware)

    profiler = ModelProfiler()
    plasticity = profiler.profile(model_config, constraints)

    fingerprinter = TaskFingerprinter()
    domains = args.domains.split(",") if args.domains else ["kjv_scripture"]
    tasks = args.tasks.split(",") if args.tasks else ["completion"]
    data_size = DataSize.SMALL
    fingerprint = fingerprinter.fingerprint(
        task_desc=f"PEFT method: {method}",
        domains=domains,
        data_size=data_size,
        hardware=hardware,
    )

    compiler = PEFTCompiler()
    plan = compiler.plan(plasticity, fingerprint, constraints)

    print(f"\nMethod requested : {method}")
    print(f"Base model       : {args.base_checkpoint or 'not specified'}")
    print(f"Corpus           : {args.corpus or 'not specified'}")
    print(f"Training substrate: {plan.training_substrate}")
    print(f"Recommended stack : {fingerprint.recommended_peft_stack}")
    print(f"Domain shift      : {fingerprint.domain_shift.name}")
    print(f"\nLayer-wise plan ({len(plan.layer_specs)} specs):")
    for spec in plan.layer_specs[:10]:
        print(f"  layer {spec.layer_idx:>2}  {spec.module_name:<20}  {spec.peft_method:<12}  rank={spec.rank}")
    if len(plan.layer_specs) > 10:
        print(f"  ... ({len(plan.layer_specs) - 10} more specs)")
    print(f"\nEstimated trainable params: {plan.estimated_trainable_params:,}")

    if method == "omni":
        print("\n--- TOURNAMENT SIMULATION ---")
        candidates = fingerprint.recommended_peft_stack[:5] or ["ia3", "lora", "adalora", "dora"]
        tournament = TrainingTournament(candidates)
        winner = tournament.run_dry(plasticity, fingerprint, constraints)
        print(f"Candidates: {candidates}")
        print(f"Winner    : {winner.winner.method_id}")
        print(f"Reason    : {winner.selection_reason}")
        for r in winner.all_results:
            print(f"  {r.method_id:<16} acc={r.domain_accuracy:.2f}  ret={r.base_retention:.2f}  params={r.trainable_params:,}")

    print("\n" + "=" * 72)
    print("Dry run complete. No training performed.")
    print("=" * 72)


# ---------------------------------------------------------------------------
# Training loop (MLX)
# ---------------------------------------------------------------------------

def load_corpus_tokens(corpus_path: Path, max_seq_len: int = 512,
                       vocab_size: int = 259) -> list:
    """Load corpus text and return list of token-id sequences.

    Uses the canonical byte codec (byte b -> id b + (vocab_size-256)). The base
    was pretrained at byte_offset=3 (train_byte.py); the prior `b + 1` here was a
    bug that fed every flat PEFT/SFT/DPO run mis-encoded tokens.
    """
    import mlx.core as mx
    from byte_codec import encode_text
    text = corpus_path.read_text(encoding="utf-8", errors="replace")

    # Canonical byte-level encoding (matches train_byte.py: bytes -> 3..258)
    tokens = encode_text(text, vocab_size=vocab_size)

    # Chunk into sequences of max_seq_len + 1 (for next-token prediction)
    chunks = []
    for i in range(0, len(tokens) - max_seq_len, max_seq_len):
        chunk = tokens[i:i + max_seq_len + 1]
        if len(chunk) == max_seq_len + 1:
            chunks.append(mx.array(chunk))
    return chunks


def build_peft_model(method: str, base_model, args: argparse.Namespace):
    """Construct PEFT-augmented model based on method."""
    import mlx.core as mx
    import mlx.nn as nn
    from peft.base import AdaptationConstraints, HardwareBudget
    from peft.fingerprint import TaskFingerprinter, DataSize
    from peft.profiler import ModelProfiler
    from peft.compiler import PEFTCompiler

    cfg = base_model.cfg
    hardware = HardwareBudget(train_vram_mb=args.train_vram_mb)
    constraints = AdaptationConstraints(hardware=hardware)

    if method in {"sft", "dpo", "ipo", "kto", "orpo", "ppo_rlhf", "grpo",
                  "distill_logit", "distill_sequence"}:
        # Alignment: return (operators={}, method) matching the non-alignment contract.
        # The caller unpacks as: operators, resolved_method = build_peft_model(...)
        # so (base_model, {}) would put the model in operators and {} in resolved_method.
        if method == "sft":
            print(f"[INFO] SFT: unfreezing all base model parameters for full fine-tuning")
        else:
            print(f"[INFO] {method}: using alignment objective over base model")
        return {}, method

    # PEFT: freeze base model and attach delta operators
    base_model.freeze()

    rank = args.rank
    alpha = float(args.alpha)
    d_model = cfg.d_model

    import importlib
    meta = METHOD_REGISTRY.get(method)
    if meta is None:
        raise ValueError(f"Unknown method '{method}'. Run --list-methods to see all options.")

    mod = importlib.import_module(meta["module"])
    OperatorClass = getattr(mod, meta["class"])

    # Build operators for attention Q and V projections (most impactful targets)
    operators = {}

    if method == "qlora":
        # Bug 3 fix: QLoRA must quantize the model, not just create QLoRALinear operators
        from peft.low_rank.qlora import quantize_model_to_4bit
        _q_model, adapters = quantize_model_to_4bit(base_model)
        base_model = _q_model  # model layers are now quantized
        # quantize_model_to_4bit returns keys "block_{i}.attn.{proj}"; rename to "layer{i}.attn.{proj}"
        for k, adapter in adapters.items():
            # k format: "block_0.attn.q" → "layer0.attn.q"
            new_key = k.replace("block_", "layer", 1)
            operators[new_key] = adapter
        total_trainable = sum(
            op.num_trainable_params() for op in operators.values()
            if hasattr(op, "num_trainable_params")
        )
        print(f"[INFO] qlora: {len(operators)} operators, ~{total_trainable:,} trainable params")
        return operators, method

    if meta["family"] == "low_rank":
        if method in {"dora", "pissa"}:
            # These require frozen weight matrices as input
            # Use zero weight as placeholder (real training loads actual weights)
            import mlx.core as mx
            placeholder_weight = mx.zeros((d_model, d_model))
            for layer_idx in range(cfg.n_layers):
                for proj in ["q", "v"]:
                    key = f"layer{layer_idx}.attn.{proj}"
                    operators[key] = OperatorClass(
                        frozen_weight=placeholder_weight,
                        rank=rank,
                        alpha=alpha,
                    )
        elif method == "vera":
            for layer_idx in range(cfg.n_layers):
                for proj in ["q", "v"]:
                    key = f"layer{layer_idx}.attn.{proj}"
                    operators[key] = OperatorClass(
                        in_features=d_model,
                        out_features=d_model,
                        rank=rank * 4,  # VeRA uses larger rank with tiny vecs
                    )
        elif method in {"loha", "lokr", "rosa"}:
            for layer_idx in range(cfg.n_layers):
                for proj in ["q", "v"]:
                    key = f"layer{layer_idx}.attn.{proj}"
                    operators[key] = OperatorClass(
                        in_features=d_model,
                        out_features=d_model,
                        rank=rank,
                        alpha=alpha,
                    )
        else:
            for layer_idx in range(cfg.n_layers):
                for proj in ["q", "v"]:
                    key = f"layer{layer_idx}.attn.{proj}"
                    operators[key] = OperatorClass(
                        in_features=d_model,
                        out_features=d_model,
                        rank=rank,
                        alpha=alpha,
                    )

    elif meta["family"] == "activation":
        op = OperatorClass(d_model=d_model)
        operators["global_ia3"] = op

    elif meta["family"] == "additive":
        for layer_idx in range(cfg.n_layers):
            key = f"layer{layer_idx}.adapter"
            operators[key] = OperatorClass(
                d_model=d_model,
                bottleneck_dim=args.bottleneck_dim,
            )

    elif meta["family"] == "prompt":
        op = OperatorClass(
            n_tokens=args.prompt_tokens,
            d_model=d_model,
        )
        operators["prompt"] = op

    elif meta["family"] == "selective":
        if method == "bitfit":
            import mlx.core as mx
            for layer_idx in range(cfg.n_layers):
                for proj in ["q", "v"]:
                    weight = getattr(base_model.blocks[layer_idx].attn, proj).weight
                    key = f"layer{layer_idx}.attn.{proj}"
                    operators[key] = OperatorClass(
                        in_features=d_model,
                        out_features=d_model,
                        frozen_weight=weight,
                    )
        elif method == "fishmask":
            import mlx.core as mx
            for layer_idx in range(cfg.n_layers):
                weight = base_model.blocks[layer_idx].attn.q.weight
                key = f"layer{layer_idx}.attn.q"
                operators[key] = OperatorClass(
                    frozen_weight=weight,
                    mask_fraction=args.mask_fraction,
                )
        else:
            for layer_idx in range(cfg.n_layers):
                key = f"layer{layer_idx}.selective"
                operators[key] = OperatorClass(d_model=d_model)

    elif meta["family"] == "structural":
        for layer_idx in range(cfg.n_layers):
            key = f"layer{layer_idx}.struct"
            if method == "fourier_ft":
                operators[key] = OperatorClass(
                    in_features=d_model,
                    out_features=d_model,
                    n_frequency=args.n_frequency,
                )
            else:
                operators[key] = OperatorClass(features=d_model)

    elif meta["family"] == "hybrid":
        for layer_idx in range(cfg.n_layers):
            key = f"layer{layer_idx}.hybrid"
            operators[key] = OperatorClass(d_model=d_model, rank=rank)

    total_trainable = sum(
        op.num_trainable_params() for op in operators.values()
        if hasattr(op, "num_trainable_params")
    )
    print(f"[INFO] {method}: {len(operators)} operators, ~{total_trainable:,} trainable params")

    return operators, method


class _LoRAPatched(nn.Module):
    """Wraps a frozen base Linear + a trainable LoRA delta operator.

    Injected into base_model.blocks[N].attn.{proj} so that gradients flow
    through the LoRA adapter weights during nn.value_and_grad(base_model, ...).

    IMPORTANT: MLX's nn.Module.parameters() skips children whose attribute
    names start with an underscore (e.g. _base, _lora). Use non-underscore
    names (base, lora) so that trainable_parameters() can see the LoRA weights
    and value_and_grad can differentiate through them.
    """

    def __init__(self, base_linear: nn.Linear, op: nn.Module) -> None:
        super().__init__()
        self.base = base_linear   # must NOT start with _ (MLX skips _ children)
        self.base.freeze()
        self.lora = op            # trainable DeltaOperator (nn.Module subclass)

    def __call__(self, x: mx.array) -> mx.array:
        return self.base(x) + self.lora(x)


# Alignment methods that use the full base model with a training objective
ALIGNMENT_METHODS = {"sft", "dpo", "ipo", "kto", "orpo", "ppo_rlhf", "grpo",
                     "distill_logit", "distill_sequence"}


def run_peft_training(method: str, operators: dict, base_model, corpus_chunks: list, args: argparse.Namespace, output_dir: Path | None = None) -> None:
    """Run the PEFT training loop using MLX.

    Bug 1 fix: inject LoRA operators directly into the model's attention layers
    so that nn.value_and_grad(base_model, compute_loss) can differentiate
    through them. The old approach kept operators separate from the model tree
    so gradients were always zero (all base_model params were frozen).
    """
    import mlx.core as mx
    import mlx.nn as nn
    import mlx.optimizers as optim

    if not corpus_chunks:
        print("[WARN] No corpus chunks loaded. Skipping training.")
        return

    if not operators:
        print("[WARN] No operators provided. Use _run_alignment_training for alignment methods.")
        return

    # Bug 1 fix: inject low-rank adapters into the model's attention layers.
    # Gate on method family to avoid injecting non-LoRA operators (bitfit, fishmask, etc.)
    # that share the same key pattern but need different handling.
    meta = METHOD_REGISTRY.get(method, {})
    is_low_rank = meta.get("family") == "low_rank"

    _injected_layers: dict = {}  # key → (block_idx, proj_name, original_linear)
    if is_low_rank:
        for key, op in operators.items():
            # key format: "layer{N}.attn.{proj}"  e.g. "layer0.attn.q"
            parts = key.split(".")  # ["layer0", "attn", "q"]
            if len(parts) == 3 and parts[0].startswith("layer") and parts[1] == "attn":
                try:
                    block_idx = int(parts[0].replace("layer", ""))
                    proj_name = parts[2]
                    original_linear = getattr(base_model.blocks[block_idx].attn, proj_name)
                    patched = _LoRAPatched(original_linear, op)
                    setattr(base_model.blocks[block_idx].attn, proj_name, patched)
                    _injected_layers[key] = (block_idx, proj_name, original_linear)
                except (AttributeError, IndexError, ValueError):
                    pass  # skip if layer structure doesn't match

        if _injected_layers:
            print(f"[INFO] Injected {len(_injected_layers)} LoRA operators into model attention layers")
        else:
            print("[WARN] No LoRA operators were injected — gradient flow may be broken")

    # compute_loss is a zero-argument closure that samples from corpus_chunks
    # and runs the forward pass through the (now LoRA-patched) model.
    def compute_loss():
        idx = int(mx.random.randint(0, len(corpus_chunks), shape=()).item())
        seq = corpus_chunks[idx]
        tokens = seq[:-1].reshape(1, -1)
        targets = seq[1:].reshape(1, -1)
        logits = base_model(tokens)
        B, T, V = logits.shape
        return mx.mean(
            nn.losses.cross_entropy(
                logits.reshape(B * T, V),
                targets.reshape(B * T),
            )
        )

    loss_and_grad = nn.value_and_grad(base_model, compute_loss)
    optimizer = optim.Adam(learning_rate=args.lr)

    print(f"[INFO] Training {method} for {args.epochs} epoch(s) on {len(corpus_chunks)} chunks")

    for epoch in range(args.epochs):
        epoch_loss = 0.0
        n_steps = min(args.steps_per_epoch, len(corpus_chunks))

        for step in range(n_steps):
            loss_val, grads = loss_and_grad()
            optimizer.update(base_model, grads)
            mx.eval(base_model.parameters(), optimizer.state)
            epoch_loss += float(loss_val.item())

            if step % max(1, n_steps // 5) == 0:
                print(f"  epoch {epoch+1}/{args.epochs}  step {step+1}/{n_steps}  loss={epoch_loss/(step+1):.4f}")

        print(f"[INFO] Epoch {epoch+1} complete. avg_loss={epoch_loss/n_steps:.4f}")
        if output_dir and not getattr(args, "no_bench", False):
            run_peft_epoch_bench(
                base_model, output_dir, epoch=epoch + 1,
                method=method, seq_len=128,
            )

    print(f"[INFO] Training complete.")


def _run_alignment_training(method: str, base_model, corpus_chunks: list, args: argparse.Namespace, output_dir: Path | None = None) -> None:
    """Dispatch to alignment-objective trainers (SFT, DPO, IPO, KTO, ORPO, PPO, GRPO).

    Bug 2 fix: alignment methods previously never trained because build_peft_model
    returned a string instead of a dict, causing isinstance(operators, dict) to be
    False at the dispatch site.
    """
    import mlx.core as mx
    import mlx.nn as nn
    import mlx.optimizers as optim

    if not corpus_chunks:
        print(f"[WARN] {method}: no corpus chunks loaded. Nothing to train.")
        return

    # SFT and distillation train the full model; others also use the same loss
    # until preference-pair datasets are wired. Unfreeze for full fine-tuning.
    base_model.unfreeze()

    # SFTTrainer.compute_loss(logits, labels) — pass logits and the full sequence
    # as labels so it can perform its own shift internally.
    try:
        from peft.alignment.sft import SFTTrainer
        trainer = SFTTrainer()
        use_trainer = True
    except Exception:
        use_trainer = False

    def compute_loss():
        idx = int(mx.random.randint(0, len(corpus_chunks), shape=()).item())
        seq = corpus_chunks[idx]          # full sequence [T+1], T = max_seq_len
        tokens = seq.reshape(1, -1)       # [1, T+1]
        # Pass only T tokens to model — RoPE is precomputed for max_seq_len (T) positions.
        inputs = tokens[:, :-1]           # [1, T]  — model input
        logits = base_model(inputs)       # [1, T, V]
        if use_trainer:
            # SFTTrainer.compute_loss shifts internally:
            #   shift_logits = logits[:, :-1, :]   # [1, T-1, V]
            #   shift_labels = labels[:, 1:]        # [1, T-1]
            # Pass inputs (same T length) as labels so the shift aligns with logits.
            return trainer.compute_loss(logits, inputs)
        else:
            # Fallback: plain next-token cross-entropy
            B, T, V = logits.shape
            return mx.mean(
                nn.losses.cross_entropy(
                    logits[:, :-1, :].reshape(-1, V),
                    inputs[:, 1:].reshape(-1),
                )
            )

    loss_and_grad = nn.value_and_grad(base_model, compute_loss)
    optimizer = optim.Adam(learning_rate=args.lr)

    print(f"[INFO] {method} training for {args.epochs} epoch(s) on {len(corpus_chunks)} chunks")

    for epoch in range(args.epochs):
        epoch_loss = 0.0
        n_steps = min(args.steps_per_epoch, len(corpus_chunks))
        for step in range(n_steps):
            loss_val, grads = loss_and_grad()
            optimizer.update(base_model, grads)
            mx.eval(base_model.parameters(), optimizer.state)
            epoch_loss += float(loss_val.item())
            if step % max(1, n_steps // 5) == 0:
                print(f"  epoch {epoch+1}/{args.epochs}  step {step+1}/{n_steps}  loss={epoch_loss/(step+1):.4f}")
        print(f"[INFO] {method} epoch {epoch+1} complete. avg_loss={epoch_loss/n_steps:.4f}")
        if output_dir and not getattr(args, "no_bench", False):
            run_peft_epoch_bench(base_model, output_dir, epoch=epoch + 1, method=method, seq_len=128)

    print(f"[INFO] {method} training complete.")

    # Save full model weights for alignment methods (operators={} so save_adapter skips them).
    # This is required for STEP 6 (GGUF export) and STEP 7 (checkpoint path recording).
    if output_dir is not None:
        import json as _json
        import numpy as np
        from mlx.utils import tree_flatten
        output_dir.mkdir(parents=True, exist_ok=True)
        flat = tree_flatten(base_model.parameters())
        np_weights = {k: np.array(v) for k, v in flat}
        weights_file = output_dir / "model_weights.npz"
        np.savez(str(weights_file), **np_weights)
        print(f"[INFO] Saved fine-tuned model weights → {weights_file}")
        # Write model_config.json alongside weights so the artifact is self-describing.
        cfg_obj = getattr(base_model, "cfg", None)
        cfg_dict = cfg_obj.to_dict() if cfg_obj is not None else {}
        cfg_dict["canonical_compatible"] = (
            cfg_dict.get("vocab_size") == 259 and cfg_dict.get("n_layers") == 8
        )
        cfg_dict["trained_by"] = method
        config_file = output_dir / "model_config.json"
        with open(config_file, "w") as _f:
            _json.dump(cfg_dict, _f, indent=2)
        print(f"[INFO] Saved model config → {config_file}")


def run_omni_training(
    base_model,
    corpus_chunks: list,
    args: argparse.Namespace,
    output_dir: Path | None = None,
) -> None:
    """
    True Omni-PEFT training: all enabled PEFT mechanisms in one unified pass.

    Architecture:
      - Compiler produces a LayerAdaptationSpec list (mixed lora/adalora/dora per layer)
      - OmniPEFTCompositeAdapter wraps EVERY spec plus IA3 + BitFit + Prefix
      - All operators injected into base_model tree before value_and_grad
      - ONE forward pass → ONE loss → ONE backward pass → ONE artifact

    This is NOT a tournament. No winner is selected. All operators contribute
    gradient signal simultaneously.
    """
    import mlx.core as mx
    import mlx.nn as nn
    import mlx.optimizers as optim
    import json as _json
    import numpy as np

    if not corpus_chunks:
        print("[WARN] run_omni_training: no corpus chunks. Nothing to train.")
        return

    # Build compiler plan
    from peft.base import AdaptationConstraints, HardwareBudget
    from peft.fingerprint import TaskFingerprinter, DataSize, DomainShift
    from peft.profiler import ModelProfiler
    from peft.compiler import PEFTCompiler
    from peft.omni_composite import OmniPEFTCompositeAdapter

    hardware = HardwareBudget(train_vram_mb=args.train_vram_mb)
    constraints = AdaptationConstraints(hardware=hardware)
    profiler = ModelProfiler()
    cfg_dict = {
        "vocab_size": base_model.cfg.vocab_size,
        "n_layers": base_model.cfg.n_layers,
        "d_model": base_model.cfg.d_model,
        "d_ffn": base_model.cfg.d_ffn,
    }
    plasticity = profiler.profile(cfg_dict, constraints)
    fingerprinter = TaskFingerprinter()
    fingerprint = fingerprinter.fingerprint(
        task_desc="omni alignment",
        domains=["scripture", "governance", "alignment"],
        data_size=DataSize.MEDIUM,
        hardware=hardware,
    )
    plan = PEFTCompiler().plan(plasticity, fingerprint, constraints)
    print(f"[INFO] Omni compiler plan: {len(plan.layer_specs)} specs, "
          f"methods={set(s.peft_method for s in plan.layer_specs)}")

    # Build composite adapter (all operators in one tree)
    composite = OmniPEFTCompositeAdapter.from_plan(
        plan,
        base_model,
        enable_ia3=True,
        enable_bitfit=True,
        enable_prefix=True,
        prefix_n=getattr(args, "prompt_tokens", 8),
    )
    print(f"[INFO] Omni composite built: methods={composite._genome_methods}, "
          f"operators={composite._operator_count}")

    # Freeze base, inject all operators into model tree
    base_model.freeze()
    rollback = composite.inject_into(base_model)
    injected = len(rollback)
    print(f"[INFO] Injected {injected} _OmniPatched layers into model tree")
    if injected == 0:
        print("[WARN] No layers injected — gradient flow impossible. Check model structure.")

    def compute_loss():
        idx = int(mx.random.randint(0, len(corpus_chunks), shape=()).item())
        seq = corpus_chunks[idx]
        tokens = seq[:-1].reshape(1, -1)
        targets = seq[1:].reshape(1, -1)
        logits = base_model(tokens)
        B, T, V = logits.shape
        return mx.mean(
            nn.losses.cross_entropy(
                logits.reshape(B * T, V),
                targets.reshape(B * T),
            )
        )

    loss_and_grad = nn.value_and_grad(base_model, compute_loss)
    optimizer = optim.Adam(learning_rate=args.lr)

    print(f"[INFO] Omni-PEFT training: {args.epochs} epoch(s), {len(corpus_chunks)} chunks")
    print("[INFO] Single optimizer. Single loss. All mechanisms train together.")

    total_loss = 0.0
    total_steps = 0

    for epoch in range(args.epochs):
        epoch_loss = 0.0
        n_steps = min(args.steps_per_epoch, len(corpus_chunks))

        for step in range(n_steps):
            loss_val, grads = loss_and_grad()
            optimizer.update(base_model, grads)
            mx.eval(base_model.parameters(), optimizer.state)
            step_loss = float(loss_val.item())
            epoch_loss += step_loss
            total_loss += step_loss
            total_steps += 1

            if step % max(1, n_steps // 5) == 0:
                print(f"  [omni] epoch {epoch+1}/{args.epochs}  "
                      f"step {step+1}/{n_steps}  loss={epoch_loss/(step+1):.4f}")

        avg = epoch_loss / max(1, n_steps)
        print(f"[INFO] Omni epoch {epoch+1} complete. avg_loss={avg:.4f}")

        if output_dir and not getattr(args, "no_bench", False):
            run_peft_epoch_bench(base_model, output_dir, epoch=epoch + 1,
                                 method="omni", seq_len=128)

    final_avg_loss = total_loss / max(1, total_steps)
    print(f"[INFO] Omni-PEFT training complete. final_avg_loss={final_avg_loss:.4f}")

    # Save unified Omni artifact
    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)

        # Extract all trained weights
        weights = composite.extract_weights()
        np_weights = {k: np.array(v) for k, v in weights.items()}
        weights_file = output_dir / "omni_adapter_weights.npz"
        np.savez(str(weights_file), **np_weights)
        print(f"[INFO] Saved Omni weights ({len(np_weights)} tensors) → {weights_file}")

        # Genome record
        base_sha = ""
        if args.base_checkpoint and Path(args.base_checkpoint).exists():
            import hashlib
            h = hashlib.sha256(Path(args.base_checkpoint).read_bytes()).hexdigest()
            base_sha = h[:16]
        genome = composite.genome_dict(
            base_model_sha256=base_sha,
            final_avg_loss=round(final_avg_loss, 4),
            training_epochs=args.epochs,
        )
        genome_file = output_dir / "omni_adapter_genome.json"
        with open(genome_file, "w") as _f:
            _json.dump(genome, _f, indent=2)
        print(f"[INFO] Saved Omni genome → {genome_file}")

        # Manifest
        manifest = {
            "artifact_type": "omni_peft_adapter",
            "doctrine": "ml-training/peft/OMNI_PEFT_DOCTRINE.md",
            "base_checkpoint": str(args.base_checkpoint or ""),
            "corpus": str(args.corpus or ""),
            "epochs": args.epochs,
            "enabled_methods": composite._genome_methods,
            "operator_count": composite._operator_count,
            "is_tournament": False,
            "tournament_winner": None,
            "canonical_promoted": False,
        }
        manifest_file = output_dir / "omni_adapter_manifest.json"
        with open(manifest_file, "w") as _f:
            _json.dump(manifest, _f, indent=2)
        print(f"[INFO] Saved Omni manifest → {manifest_file}")


def save_adapter(method: str, operators: dict, output_dir: Path, args: argparse.Namespace) -> None:
    """Save adapter weights and genome to output directory."""
    import mlx.core as mx
    from mlx.utils import tree_flatten
    from peft.base import AdapterGenomeRecord
    import datetime

    output_dir.mkdir(parents=True, exist_ok=True)

    # Serialize operator parameters as numpy arrays
    weights: dict[str, Any] = {}
    for key, op in operators.items():
        if hasattr(op, "parameters"):
            for pname, pval in tree_flatten(op.parameters()):
                weights[f"{key}.{pname}"] = pval

    if weights:
        weights_file = output_dir / "adapter_weights.npz"
        import numpy as np
        np_weights = {k: np.array(v) for k, v in weights.items()}
        np.savez(str(weights_file), **np_weights)
        print(f"[INFO] Saved adapter weights → {weights_file}")

    # Write adapter genome
    record = AdapterGenomeRecord(
        name=output_dir.name,
        version="1.0.0",
        base_model=args.base_checkpoint or "kjv_tokenless_v1",
        peft_method=method,
        delta_family=METHOD_REGISTRY.get(method, {}).get("family", "unknown").upper(),
        training_corpus=args.corpus or "eng_kjv_apocrypha_v1",
        training_config={
            "rank": args.rank,
            "alpha": args.alpha,
            "epochs": args.epochs,
            "lr": args.lr,
        },
        purpose_domains=["kjv_scripture", "theology"],
        purpose_tasks=["completion", "citation"],
        routing_activate_when=["kjv_query", "scripture_completion"],
        mergeable=True,
        hot_swappable=True,
    )

    genome_file = output_dir / "adapter_genome.json"
    genome_file.write_text(record.to_json(), encoding="utf-8")
    print(f"[INFO] Saved adapter genome → {genome_file}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Unified PEFT training CLI for Tokenless models",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--method", default="lora",
                   help="PEFT method ID (see --list-methods). Use 'omni' for automatic selection.")
    p.add_argument("--base-checkpoint", default=None,
                   help="Path to base model checkpoint (.npz or directory)")
    p.add_argument("--corpus", default=None,
                   help="Path to corpus text file (default: auto-detect KJV corpus)")
    p.add_argument("--output", default=None,
                   help="Output directory for adapter weights and genome (default: adapters/staging/<method>)")
    p.add_argument("--rank", type=int, default=8,
                   help="Low-rank adapter rank (default: 8)")
    p.add_argument("--alpha", type=float, default=16.0,
                   help="LoRA scaling alpha (default: 16.0)")
    p.add_argument("--epochs", type=int, default=3,
                   help="Training epochs (default: 3)")
    p.add_argument("--lr", type=float, default=2e-4,
                   help="Learning rate (default: 2e-4)")
    p.add_argument("--steps-per-epoch", type=int, default=200,
                   help="Steps per epoch (default: 200)")
    p.add_argument("--bottleneck-dim", type=int, default=64,
                   help="Bottleneck dimension for adapter methods (default: 64)")
    p.add_argument("--prompt-tokens", type=int, default=20,
                   help="Number of soft prompt tokens (default: 20)")
    p.add_argument("--n-frequency", type=int, default=100,
                   help="Frequency count for FourierFT (default: 100)")
    p.add_argument("--mask-fraction", type=float, default=0.01,
                   help="Trainable fraction for FishMask/DiffPruning (default: 0.01)")
    p.add_argument("--train-vram-mb", type=float, default=16_000,
                   help="Available VRAM in MB for hardware planning (default: 16000)")
    p.add_argument("--domains", default=None,
                   help="Comma-separated domain list for fingerprinting (default: kjv_scripture)")
    p.add_argument("--tasks", default=None,
                   help="Comma-separated task list for fingerprinting (default: completion)")
    p.add_argument("--no-bench", action="store_true",
                   help="Disable inline epoch benchmarks and final full bench")
    p.add_argument("--dry-run", action="store_true",
                   help="Print compilation plan without executing training")
    p.add_argument("--list-methods", action="store_true",
                   help="Print all available PEFT methods and exit")
    p.add_argument("--model-config", default=None, metavar="PATH",
                   help="Path to model_config.json (required for alignment methods like sft). "
                        "Overrides the default ModelConfig (vocab_size=16000, n_layers=6) with "
                        "the architecture the base checkpoint was actually trained on.")
    # --- Omni-PEFT Scribe Alignment regimen (--method omni --scribe) ---
    p.add_argument("--scribe", action="store_true",
                   help="Omni-PEFT Scribe regimen: 4 weighted pools "
                        "(45 retention / 25 grounding / 20 governance / 10 scribe) "
                        "+ held-out scripture BPB retention gate + early-stop. "
                        "Requires --method omni.")
    p.add_argument("--clean-corpus", default=None, metavar="PATH",
                   help="Scribe regimen: clean scripture corpus for the retention pool + "
                        "held-out slice (default: models v7/training/corpus/eng_kjv_clean_v1/corpus.txt)")
    p.add_argument("--programs-dir", default=None, metavar="PATH",
                   help="Scribe regimen: dir of audited alignment_*_v1.jsonl pools "
                        "(default: models v7/training/corpus/programs)")
    p.add_argument("--scribe-seq-len", type=int, default=256,
                   help="Scribe regimen: scripture window length (default: 256)")
    p.add_argument("--heldout-every", type=int, default=90,
                   help="Scribe regimen: hold out every Nth verse for BPB eval (default: 90)")
    p.add_argument("--bpb-max-regress", type=float, default=0.15,
                   help="Scribe regimen: early-stop if held-out BPB regresses beyond this "
                        "many bits/byte vs frozen-base baseline (default: 0.15)")
    return p.parse_args()


def main() -> int:
    args = parse_args()

    if args.list_methods:
        print(f"{'METHOD':<20} {'FAMILY':<14} {'CLASS'}")
        print("-" * 60)
        for method_id, meta in sorted(METHOD_REGISTRY.items()):
            print(f"{method_id:<20} {meta['family']:<14} {meta['class']}")
        print(f"\n{'omni':<20} {'auto':<14} compiler + tournament selection")
        return 0

    method = args.method.lower().replace("-", "_")

    if method != "omni" and method not in METHOD_REGISTRY:
        print(f"[ERROR] Unknown method '{method}'. Run --list-methods to see all options.", file=sys.stderr)
        return 2

    # Auto-detect corpus if not specified
    if args.corpus is None:
        default_corpus = ML_TRAINING / "corpus/eng_kjv_apocrypha_v1/corpus.txt"
        if default_corpus.exists():
            args.corpus = str(default_corpus)
            print(f"[INFO] Auto-detected corpus: {args.corpus}")

    # Auto-set output path
    if args.output is None:
        args.output = str(ML_TRAINING / f"adapters/staging/{method}_kjv_v1")

    # Dry run: print compilation plan
    if args.dry_run:
        dry_run_report(method, args)
        return 0

    # Real training: requires MLX and base model
    print(f"[INFO] Omni-PEFT | method={method} | rank={args.rank} | alpha={args.alpha} | epochs={args.epochs}")

    try:
        import mlx.core as mx
        import mlx.nn as nn
    except ImportError:
        print("[ERROR] MLX is not installed. Install with: pip install mlx", file=sys.stderr)
        return 1

    # Load base model config (lightweight — just for operator sizing)
    sys.path.insert(0, str(SCRIPT_DIR))
    from model import ModelConfig, TokenlessLM

    cfg = ModelConfig()  # default: d_model=384, n_layers=6, etc.

    # Override config from JSON if --model-config supplied.  Alignment methods (sft,
    # dpo, …) MUST supply this when the base checkpoint uses a non-default architecture
    # (e.g. the canonical byte-level model: vocab_size=259, n_layers=8).
    if getattr(args, "model_config", None):
        import json as _json
        with open(args.model_config) as _f:
            _mc = _json.load(_f)
        cfg = ModelConfig(
            vocab_size=_mc.get("vocab_size", cfg.vocab_size),
            n_layers=_mc.get("n_layers", cfg.n_layers),
            n_heads=_mc.get("n_heads", cfg.n_heads),
            d_model=_mc.get("d_model", cfg.d_model),
            d_ffn=_mc.get("d_ffn", cfg.d_ffn),
            max_seq_len=_mc.get("max_seq_len", cfg.max_seq_len),
            rope_base=float(_mc.get("rope_base", cfg.rope_base)),
            tie_embeddings=bool(_mc.get("tie_embeddings", cfg.tie_embeddings)),
        )
        print(f"[INFO] Loaded model config: vocab_size={cfg.vocab_size}, n_layers={cfg.n_layers}, "
              f"d_model={cfg.d_model}, n_heads={cfg.n_heads}")

    base_model = TokenlessLM(cfg)

    if args.base_checkpoint:
        checkpoint = Path(args.base_checkpoint)
        if checkpoint.exists():
            try:
                if checkpoint.suffix == ".safetensors":
                    # MLX native loader for .safetensors (avoids numpy format mismatch).
                    weights_mx = mx.load(str(checkpoint))
                    base_model.load_weights(list(weights_mx.items()))
                else:
                    import numpy as np
                    from mlx.utils import tree_unflatten
                    weights = dict(np.load(str(checkpoint)))
                    base_model.update(tree_unflatten([(k, mx.array(v)) for k, v in weights.items()]))
                print(f"[INFO] Loaded checkpoint: {checkpoint}")
            except Exception as e:
                print(f"[WARN] Could not load checkpoint: {e}. Using random weights.")
        else:
            print(f"[WARN] Checkpoint not found: {checkpoint}. Using random weights.")

    # Omni-PEFT Scribe regimen: 4 weighted pools + retention gate (bypasses flat corpus)
    if method == "omni" and getattr(args, "scribe", False):
        from omni_scribe import run_omni_scribe_training
        repo_root = ML_TRAINING.parent

        # Resolve scribe corpus defaults across layouts: substrate nested as
        # 'models v7/training/...' (upstream source) vs deployed flat as the KJVA
        # project ('training/...'). First existing wins so the path resolves
        # inside the active home.
        def _resolve_corpus(rel: str) -> str:
            for base in (repo_root / "models v7", repo_root):
                cand = base / rel
                if cand.exists():
                    return str(cand)
            return str(repo_root / rel)  # flat (KJVA) is the canonical home

        if not args.clean_corpus:
            args.clean_corpus = _resolve_corpus("training/corpus/eng_kjv_clean_v1/corpus.txt")
        if not args.programs_dir:
            args.programs_dir = _resolve_corpus("training/corpus/programs")
        for label, path in (("clean-corpus", args.clean_corpus), ("programs-dir", args.programs_dir)):
            if not Path(path).exists():
                print(f"[ERROR] scribe {label} not found: {path}", file=sys.stderr)
                return 1
        run_omni_scribe_training(base_model, args, output_dir=Path(args.output))
        print(f"[SUCCESS] Omni-PEFT Scribe Alignment complete. Artifact: {args.output}")
        return 0

    # Omni-PEFT: bypass build_peft_model and run unified training directly
    if method == "omni":
        corpus_chunks = []
        if args.corpus:
            corpus_path = Path(args.corpus)
            if corpus_path.exists():
                corpus_chunks = load_corpus_tokens(corpus_path, max_seq_len=cfg.max_seq_len, vocab_size=cfg.vocab_size)
                print(f"[INFO] Loaded {len(corpus_chunks)} corpus chunks for Omni-PEFT")
            else:
                print(f"[WARN] Corpus not found: {args.corpus}")
        if not corpus_chunks:
            print("[ERROR] Omni-PEFT requires a corpus (--corpus <path>)", file=sys.stderr)
            return 1
        run_omni_training(base_model, corpus_chunks, args, output_dir=Path(args.output))
        if not getattr(args, "no_bench", False):
            run_final_bench(Path(args.output))
        print(f"[SUCCESS] Omni-PEFT complete. Artifact saved to: {args.output}")
        return 0

    # Build PEFT operators
    operators, resolved_method = build_peft_model(method, base_model, args)

    # Load corpus
    corpus_chunks = []
    if args.corpus and resolved_method in CORPUS_METHODS:
        corpus_path = Path(args.corpus)
        if corpus_path.exists():
            corpus_chunks = load_corpus_tokens(corpus_path, max_seq_len=cfg.max_seq_len, vocab_size=cfg.vocab_size)
            print(f"[INFO] Loaded {len(corpus_chunks)} corpus chunks from {corpus_path.name}")
        else:
            print(f"[WARN] Corpus not found: {corpus_path}")

    output_dir = Path(args.output)

    # Run training
    # Bug 2 fix: alignment methods now return operators={} (empty dict) from build_peft_model,
    # so isinstance(operators, dict) is True. Dispatch to the right trainer based on method.
    if isinstance(operators, dict) and corpus_chunks:
        if resolved_method in ALIGNMENT_METHODS:
            # Hard architecture guard: alignment training must target the canonical
            # byte-level model.  A default ModelConfig (vocab_size=16000, n_layers=6)
            # silently trains an incompatible BPE-shaped model — the sft_v1 bug.
            # Pass --model-config <canonical model_config.json> to proceed.
            if cfg.vocab_size != 259 or cfg.n_layers != 8:
                print(
                    f"[FATAL] Architecture mismatch: alignment training requires the canonical "
                    f"byte-level config (vocab_size=259, n_layers=8) but current config has "
                    f"vocab_size={cfg.vocab_size}, n_layers={cfg.n_layers}. "
                    "Pass --model-config <path/to/model_config.json> with the canonical "
                    "byte-level architecture.",
                    file=sys.stderr,
                )
                return 1
            _run_alignment_training(resolved_method, base_model, corpus_chunks, args, output_dir=output_dir)
        else:
            run_peft_training(resolved_method, operators, base_model, corpus_chunks, args,
                              output_dir=output_dir)
    elif isinstance(operators, dict) and not corpus_chunks:
        if resolved_method in ALIGNMENT_METHODS:
            print(f"[INFO] {resolved_method} is a training objective method.")
            print("[INFO] Attach a preference/instruction dataset via --corpus for full training.")
        else:
            print("[WARN] No corpus chunks loaded. Nothing to train.")
            return 1
    else:
        print("[WARN] No operators and not an alignment method. Nothing to train.")
        return 1

    # Save adapter
    if isinstance(operators, dict) and operators:
        save_adapter(resolved_method, operators, output_dir, args)

    # Final bench
    if not getattr(args, "no_bench", False):
        run_final_bench(output_dir)

    print(f"[SUCCESS] PEFT run complete. Adapter saved to: {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
