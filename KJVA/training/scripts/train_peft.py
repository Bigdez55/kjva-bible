#!/usr/bin/env python3
"""
train_peft.py — Unified PEFT training CLI for Tokenless models

Unified entry point for all 37 PEFT/alignment/distillation methods.
Each method maps to a concrete DeltaOperator in training/peft/.

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


# ckpt_bench imports MLX at module load. Import it LAZILY so the MLX-free paths
# (--list-methods, --dry-run, and the distillation fail-closed guard) work without
# MLX installed; the bench is only reached inside an actual MLX training loop.
def run_peft_epoch_bench(*args, **kwargs):
    from ckpt_bench import run_peft_epoch_bench as _impl
    return _impl(*args, **kwargs)


def run_final_bench(*args, **kwargs):
    from ckpt_bench import run_final_bench as _impl
    return _impl(*args, **kwargs)

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
    "distill_logit":    {"module": "peft.alignment.distillation", "class": "DistillationLogitTrainer",    "family": "distillation"},
    "distill_sequence": {"module": "peft.alignment.distillation", "class": "DistillationSequenceTrainer", "family": "distillation"},
}

# Methods that require a corpus for training input sequences
CORPUS_METHODS = {
    "lora", "dora", "qlora", "adalora", "vera", "pissa", "rslora", "olora",
    "loha", "lokr", "rosa", "houlsby", "pfeiffer", "ia3", "bitfit",
    "diffpruning", "fishmask", "far", "unipelt", "mam_adapter", "compacter",
    "xlora", "oft", "boft", "fourier_ft", "prompt_tuning", "prefix_tuning",
    "p_tuning", "sft", "distill_logit", "distill_sequence",
}

# Methods whose delta is NOT applied at inference by the current XMIND/OmniPEFTBlock path.
# prefix_tuning trains a per-layer KV-prefix whose operator __call__ is identity — prefix-KV
# injection requires a base-attention hook that does not exist in the frozen engine (see
# peft/prompt/prefix_tuning.py "WIRING STATUS"). Training one produces a real, well-formed
# adapter that is a NO-OP at serve time. We do NOT fake it (faking would mean editing the
# frozen base attention and breaking parity); instead we WARN loudly so a prefix run is never
# silently mistaken for a deployable adapter. prompt_tuning / p_tuning ARE fully serve-wired.
SERVE_INERT_METHODS = {"prefix_tuning"}


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
    domains = args.domains.split(",") if args.domains else ["general"]
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

    Byte b -> token id b + (vocab_size - 256). The base is pretrained at
    byte_offset=3 (train_byte.py: bytes map to 3..258; ids 0/1/2 = pad/bos/eos).
    The prior `b + 1` was a bug that mis-encoded every flat PEFT/SFT/DPO run.
    """
    import mlx.core as mx
    text = corpus_path.read_text(encoding="utf-8", errors="replace")

    # Canonical byte-level encoding (matches train_byte.py)
    byte_offset = vocab_size - 256
    raw_bytes = text.encode("utf-8")
    tokens = [b + byte_offset for b in raw_bytes]

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
        # Alignment: just return the base model with frozen layers (SFT unfreezes all)
        if method == "sft":
            print(f"[INFO] SFT: unfreezing all base model parameters for full fine-tuning")
        else:
            print(f"[INFO] {method}: using alignment objective over base model")
        return base_model, method

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

    if meta["family"] == "low_rank":
        if method in {"dora", "pissa"}:
            # These require the REAL frozen attention weight as input:
            # PiSSA SVDs it, DoRA normalizes by its column norm. A zero
            # placeholder degenerates (SVD of zeros / divide-by-zero -> NaN).
            for layer_idx in range(cfg.n_layers):
                for proj in ["q", "v"]:
                    weight = getattr(base_model.blocks[layer_idx].attn, proj).weight
                    key = f"layer{layer_idx}.attn.{proj}"
                    operators[key] = OperatorClass(
                        frozen_weight=weight,
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


def run_peft_training(method: str, operators: dict, base_model, corpus_chunks: list, args: argparse.Namespace, output_dir: Path | None = None) -> None:
    """Run the PEFT training loop using MLX."""
    import mlx.core as mx
    import mlx.nn as nn
    from mlx.utils import tree_flatten
    import mlx.optimizers as optim

    if not corpus_chunks:
        print("[WARN] No corpus chunks loaded. Skipping training.")
        return

    # Collect trainable parameters from operators
    trainable_params = {}
    for key, op in operators.items():
        if hasattr(op, "parameters"):
            from mlx.utils import tree_flatten
            for pname, pval in tree_flatten(op.parameters()):
                trainable_params[f"{key}.{pname}"] = pval

    if not trainable_params:
        print("[WARN] No trainable parameters found. Check operator setup.")
        return

    optimizer = optim.Adam(learning_rate=args.lr)

    def compute_loss(params):
        # Update operator params
        for key, op in operators.items():
            if hasattr(op, "parameters"):
                from mlx.utils import tree_unflatten
                op_params = {
                    k.replace(f"{key}.", "", 1): v
                    for k, v in params.items()
                    if k.startswith(f"{key}.")
                }
                if op_params:
                    op.update(tree_unflatten(list(op_params.items())))

        # Sample random batch
        idx = int(mx.random.randint(0, len(corpus_chunks), shape=()).item())
        seq = corpus_chunks[idx]
        tokens = seq[:-1].reshape(1, -1)
        targets = seq[1:].reshape(1, -1)

        logits = base_model(tokens)

        # Cross-entropy loss
        B, T, V = logits.shape
        loss = mx.mean(
            nn.losses.cross_entropy(
                logits.reshape(B * T, V),
                targets.reshape(B * T),
            )
        )
        return loss

    loss_and_grad = nn.value_and_grad(base_model, compute_loss)

    print(f"[INFO] Training {method} for {args.epochs} epoch(s) on {len(corpus_chunks)} chunks")

    for epoch in range(args.epochs):
        epoch_loss = 0.0
        n_steps = min(args.steps_per_epoch, len(corpus_chunks))

        for step in range(n_steps):
            loss_val, grads = loss_and_grad(trainable_params)
            optimizer.update(trainable_params, grads)
            mx.eval(trainable_params)
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


def run_alignment_training(
    method: str,
    base_model,
    teacher_model,
    corpus_chunks: list,
    args: argparse.Namespace,
    output_dir: Path | None = None,
) -> None:
    """Full-base fine-tune loop for the alignment-objective family that we can train
    from a plain corpus: ``sft``, ``distill_logit``, ``distill_sequence``.

    Unlike the PEFT path (frozen base + small delta operators), these objectives
    train the WHOLE student (``base_model``) — there is no adapter to save, the
    artifact is the fine-tuned model.

    FAIL-CLOSED (gap-ledger / ADR-0002 §9.2 no-silent-mislabel): a ``distill_*``
    method REQUIRES a frozen teacher. Without one this raises — it does NOT fall
    back to next-token CE, which would silently train vanilla SFT under a
    distillation label (the exact mislabel the registry repoint was meant to
    prevent). The real KL / teacher-forced objectives live in
    ``peft.alignment.distillation`` and are CALLED here.
    """
    import mlx.core as mx
    import mlx.nn as nn
    import mlx.optimizers as optim

    if not corpus_chunks:
        print("[WARN] No corpus chunks loaded. Skipping training.")
        return

    is_distill = method in {"distill_logit", "distill_sequence"}
    if is_distill and teacher_model is None:
        raise ValueError(
            f"{method} is a knowledge-distillation objective and REQUIRES a frozen "
            f"teacher (--teacher-checkpoint). Refusing to run: without a teacher this "
            f"would silently train plain next-token cross-entropy under a distillation "
            f"label (mislabel). Provide --teacher-checkpoint, or use --method sft for "
            f"plain supervised fine-tuning."
        )

    # Bind the real distillation objective wrappers (KL @ T / teacher-forced CE).
    from peft.alignment.distillation import _shifted_hard_ce
    logit_trainer = None
    seq_trainer = None
    if method == "distill_logit":
        from peft.alignment.distillation import DistillationLogitTrainer
        logit_trainer = DistillationLogitTrainer(
            temperature=float(getattr(args, "distill_temperature", 2.0)),
            alpha=float(getattr(args, "distill_alpha", 1.0)),
        )
        print(f"[INFO] distill_logit: Hinton soft-target KL  T={logit_trainer.temperature} "
              f"alpha={logit_trainer.alpha}  (teacher frozen, stop_gradient)")
    elif method == "distill_sequence":
        from peft.alignment.distillation import DistillationSequenceTrainer
        seq_trainer = DistillationSequenceTrainer()
        print("[INFO] distill_sequence: Kim&Rush teacher-forced CE on argmax-decoded teacher tokens")
    else:
        print("[INFO] sft: full-base supervised fine-tune (shifted next-token CE)")

    # The teacher is a constant input — freeze it so no gradient is ever taken w.r.t. it
    # (belt-and-suspenders with the per-step mx.stop_gradient in the loss).
    if teacher_model is not None:
        teacher_model.freeze()

    optimizer = optim.Adam(learning_rate=args.lr)

    def loss_fn(model):
        idx = int(mx.random.randint(0, len(corpus_chunks), shape=()).item())
        seq = corpus_chunks[idx]
        tokens = seq.reshape(1, -1)
        student_logits = model(tokens)
        if method == "distill_logit":
            teacher_logits = mx.stop_gradient(teacher_model(tokens))
            return logit_trainer.compute_loss(student_logits, teacher_logits, labels=tokens)
        if method == "distill_sequence":
            teacher_logits = mx.stop_gradient(teacher_model(tokens))
            return seq_trainer.compute_loss(student_logits, teacher_logits=teacher_logits)
        # sft — teacher-free supervised next-token CE on the corpus itself
        return _shifted_hard_ce(student_logits, tokens)

    loss_and_grad = nn.value_and_grad(base_model, loss_fn)

    print(f"[INFO] Training {method} for {args.epochs} epoch(s) on {len(corpus_chunks)} chunks "
          f"(full-base fine-tune)")
    for epoch in range(args.epochs):
        epoch_loss = 0.0
        n_steps = min(args.steps_per_epoch, len(corpus_chunks))
        for step in range(n_steps):
            loss_val, grads = loss_and_grad(base_model)
            optimizer.update(base_model, grads)
            mx.eval(base_model.parameters(), optimizer.state)
            epoch_loss += float(loss_val.item())
            if step % max(1, n_steps // 5) == 0:
                print(f"  epoch {epoch+1}/{args.epochs}  step {step+1}/{n_steps}  "
                      f"loss={epoch_loss/(step+1):.4f}")
        print(f"[INFO] Epoch {epoch+1} complete. avg_loss={epoch_loss/n_steps:.4f}")
        if output_dir and not getattr(args, "no_bench", False):
            run_peft_epoch_bench(base_model, output_dir, epoch=epoch + 1, method=method, seq_len=128)
    print("[INFO] Training complete.")


def save_alignment_model(method: str, base_model, output_dir: Path, args: argparse.Namespace) -> None:
    """Persist the fine-tuned student of an alignment-objective run.

    The artifact is the full model (no adapter), written as canonical
    ``weights.safetensors`` plus a provenance JSON recording the objective and
    (for distillation) the teacher checkpoint.
    """
    import mlx.core as mx
    from mlx.utils import tree_flatten
    import datetime, json

    output_dir.mkdir(parents=True, exist_ok=True)
    flat = {k: v for k, v in tree_flatten(base_model.parameters())}
    weights_file = output_dir / "weights.safetensors"
    mx.save_safetensors(str(weights_file), flat)
    print(f"[INFO] Saved fine-tuned model → {weights_file}")

    provenance = {
        "method": method,
        "objective_family": "distillation" if method.startswith("distill_") else "sft",
        "base_checkpoint": args.base_checkpoint,
        "teacher_checkpoint": getattr(args, "teacher_checkpoint", None),
        "distill_temperature": getattr(args, "distill_temperature", None) if method == "distill_logit" else None,
        "distill_alpha": getattr(args, "distill_alpha", None) if method == "distill_logit" else None,
        "epochs": args.epochs,
        "lr": args.lr,
        "created": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    (output_dir / "alignment_provenance.json").write_text(json.dumps(provenance, indent=2))
    print(f"[INFO] Saved provenance → {output_dir / 'alignment_provenance.json'}")


def save_adapter(method: str, operators: dict, output_dir: Path, args: argparse.Namespace) -> None:
    """Save adapter weights and genome to output directory."""
    import mlx.core as mx
    from mlx.utils import tree_flatten
    from peft.base import AdapterGenomeRecord
    import datetime

    output_dir.mkdir(parents=True, exist_ok=True)

    # Serialize operator parameters under names the XMIND C engine can canonicalize.
    # build_peft_model keys low-rank operators as "layer{N}.attn.{q,k,v,o}" with LoRA
    # params A/B; xmind/src/lora.c canonicalizes "blocks.{N}.attn.{q}.A.weight" ->
    # "blk.{N}.attn_q.weight" but does NOT recognize the singular "layer{N}." form
    # (no blocks./layers. marker -> stored verbatim -> binds to nothing, applies a
    # zero delta that still loads rc=0). Emitting the canonical "blocks.{N}...A.weight"
    # name is what makes the trained adapter actually apply at inference.
    def _canonical_adapter_key(op_key: str, pname: str) -> str:
        import re as _re
        m = _re.match(r"^layer(\d+)\.(.+)$", op_key)
        if m:
            return f"blocks.{m.group(1)}.{m.group(2)}.{pname}.weight"
        return f"{op_key}.{pname}"

    weights: dict[str, Any] = {}
    for key, op in operators.items():
        if hasattr(op, "parameters"):
            for pname, pval in tree_flatten(op.parameters()):
                weights[_canonical_adapter_key(key, pname)] = pval

    if weights:
        import numpy as np
        np_weights = {k: np.array(v) for k, v in weights.items()}
        weights_file = output_dir / "adapter_weights.npz"
        np.savez(str(weights_file), **np_weights)
        print(f"[INFO] Saved adapter weights → {weights_file}")

        # Also emit the C-loadable safetensors (the absorption artifact xmind_easy_load_adapter
        # consumes). Same writer as npz_to_safetensors.py — one format of record.
        try:
            sys.path.insert(0, str(SCRIPT_DIR))
            from npz_to_safetensors import write_safetensors
            st_path = output_dir / "adapter.safetensors"
            n = write_safetensors(np_weights, st_path, alpha=float(args.alpha))
            print(f"[INFO] Saved C-loadable adapter → {st_path} ({n} tensors)")
        except Exception as e:  # noqa: BLE001
            print(f"[WARN] safetensors export skipped: {e}")

    # Write adapter genome
    record = AdapterGenomeRecord(
        name=output_dir.name,
        version="1.0.0",
        base_model=args.base_checkpoint or "base_tokenless_v1",
        peft_method=method,
        delta_family=METHOD_REGISTRY.get(method, {}).get("family", "unknown").upper(),
        training_corpus=args.corpus or "domain_corpus_v1",
        training_config={
            "rank": args.rank,
            "alpha": args.alpha,
            "epochs": args.epochs,
            "lr": args.lr,
        },
        purpose_domains=["general"],
        purpose_tasks=["completion"],
        routing_activate_when=["domain_query", "completion"],
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
                   help="Path to corpus text file (default: auto-detect under corpus/domain_corpus_v1/)")
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
    p.add_argument("--teacher-checkpoint", default=None,
                   help="Path to a FROZEN teacher checkpoint (.safetensors/.npz). REQUIRED for "
                        "distill_logit/distill_sequence — without it those methods refuse to run "
                        "rather than silently degrade to plain CE under a distillation label.")
    p.add_argument("--distill-temperature", type=float, default=2.0,
                   help="Softmax temperature T for logit distillation soft targets (default: 2.0)")
    p.add_argument("--distill-alpha", type=float, default=1.0,
                   help="Weight on the soft-KL term for logit distillation; (1-alpha) weights the "
                        "hard next-token CE. 1.0 = pure distillation, no gold labels needed (default: 1.0)")
    p.add_argument("--domains", default=None,
                   help="Comma-separated domain list for fingerprinting (default: general)")
    p.add_argument("--tasks", default=None,
                   help="Comma-separated task list for fingerprinting (default: completion)")
    p.add_argument("--no-bench", action="store_true",
                   help="Disable inline epoch benchmarks and final full bench")
    p.add_argument("--dry-run", action="store_true",
                   help="Print compilation plan without executing training")
    p.add_argument("--list-methods", action="store_true",
                   help="Print all available PEFT methods and exit")
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
        default_corpus = ML_TRAINING / "corpus/domain_corpus_v1/corpus.txt"
        if default_corpus.exists():
            args.corpus = str(default_corpus)
            print(f"[INFO] Auto-detected corpus: {args.corpus}")

    # Auto-set output path
    if args.output is None:
        args.output = str(ML_TRAINING / f"adapters/staging/{method}_v1")

    # Dry run: print compilation plan
    if args.dry_run:
        dry_run_report(method, args)
        return 0

    # FAIL-CLOSED, fail-FAST (ADR-0002 §9.2 no-silent-mislabel): a distillation objective without
    # a teacher must refuse BEFORE any model work, never degrade to teacher-less CE under a
    # distillation label. Checked here (pre-MLX) so the refusal is fast and testable without MLX;
    # run_alignment_training re-asserts it as defense-in-depth.
    if method in {"distill_logit", "distill_sequence"} and not args.teacher_checkpoint:
        print(f"[ERROR] {method} is a knowledge-distillation objective and REQUIRES a frozen teacher "
              f"(--teacher-checkpoint). Refusing to run: without a teacher this would silently train "
              f"plain next-token cross-entropy under a distillation label. Provide "
              f"--teacher-checkpoint, or use --method sft for plain supervised fine-tuning.",
              file=sys.stderr)
        return 2

    # Serve-inert honesty (ADR-0002 §11 no-silent-mislabel): a prefix-KV method trains fine but
    # its delta is NOT applied by the current frozen-engine inference path. Warn loudly so the
    # resulting adapter is never mistaken for deployable. (Not fatal — training a research
    # artifact is legitimate; silently shipping a no-op adapter is not.)
    if method in SERVE_INERT_METHODS:
        print(f"[WARN] '{method}' is SERVE-INERT in this engine: it trains a valid adapter, but its "
              f"prefix-KV delta is NOT applied at inference (the base-attention KV-prefix hook does "
              f"not exist; see peft/prompt/prefix_tuning.py WIRING STATUS). The saved adapter is a "
              f"training/research artifact, NOT a deployable serve-time adapter. Use prompt_tuning or "
              f"p_tuning for a fully serve-wired soft-prompt method.", file=sys.stderr)

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
    base_model = TokenlessLM(cfg)

    if args.base_checkpoint:
        checkpoint = Path(args.base_checkpoint)
        # FAIL CLOSED: the user explicitly asked to fine-tune a base. A missing/unloadable
        # checkpoint previously printed [WARN] and silently TRAINED ON RANDOM WEIGHTS — producing
        # a garbage adapter that looks fine. A base load failure now hard-stops.
        if not checkpoint.exists():
            print(f"[ERROR] Base checkpoint not found: {checkpoint} (refusing to train on random "
                  f"weights).", file=sys.stderr)
            return 2
        try:
            from mlx.utils import tree_unflatten
            # mx.load reads BOTH .safetensors and .npz (np.load could NOT read safetensors — that
            # was the silent-random-weights trap for the canonical safetensors base).
            weights = dict(mx.load(str(checkpoint)))
            base_model.update(tree_unflatten(list(weights.items())))
            print(f"[INFO] Loaded checkpoint: {checkpoint}")
        except Exception as e:
            print(f"[ERROR] Could not load base checkpoint {checkpoint}: {e} (refusing to train on "
                  f"random weights).", file=sys.stderr)
            return 2

    # Load the FROZEN teacher (knowledge distillation only). Same fail-closed discipline as the
    # base: a declared-but-unloadable teacher hard-stops rather than degrading to teacher-less CE.
    teacher_model = None
    if args.teacher_checkpoint:
        teacher_path = Path(args.teacher_checkpoint)
        if not teacher_path.exists():
            print(f"[ERROR] Teacher checkpoint not found: {teacher_path}", file=sys.stderr)
            return 2
        try:
            from mlx.utils import tree_unflatten
            teacher_model = TokenlessLM(cfg)
            t_weights = dict(mx.load(str(teacher_path)))
            teacher_model.update(tree_unflatten(list(t_weights.items())))
            teacher_model.freeze()
            print(f"[INFO] Loaded FROZEN teacher: {teacher_path}")
        except Exception as e:
            print(f"[ERROR] Could not load teacher checkpoint {teacher_path}: {e}", file=sys.stderr)
            return 2

    # Build PEFT operators
    operators, resolved_method = build_peft_model(method, base_model, args)

    # Load corpus
    corpus_chunks = []
    if args.corpus and resolved_method in CORPUS_METHODS:
        corpus_path = Path(args.corpus)
        if corpus_path.exists():
            corpus_chunks = load_corpus_tokens(corpus_path, max_seq_len=cfg.max_seq_len)
            print(f"[INFO] Loaded {len(corpus_chunks)} corpus chunks from {corpus_path.name}")
        else:
            print(f"[WARN] Corpus not found: {corpus_path}")

    output_dir = Path(args.output)

    # Alignment objectives we can train from a plain corpus: full-base fine-tune (sft) or real
    # knowledge distillation against a frozen teacher (distill_logit/distill_sequence). These
    # return the BASE MODEL from build_peft_model (not an operator dict), so they are routed here
    # explicitly — and run_alignment_training FAILS CLOSED for distill_* without a teacher.
    CORPUS_ALIGNMENT_METHODS = {"sft", "distill_logit", "distill_sequence"}

    # Run training
    if resolved_method in CORPUS_ALIGNMENT_METHODS and corpus_chunks:
        run_alignment_training(resolved_method, base_model, teacher_model, corpus_chunks, args,
                               output_dir=output_dir)
        save_alignment_model(resolved_method, base_model, output_dir, args)
    elif isinstance(operators, dict) and corpus_chunks:
        run_peft_training(resolved_method, operators, base_model, corpus_chunks, args,
                          output_dir=output_dir)
    elif resolved_method in {"sft", "dpo", "ipo", "kto", "orpo", "ppo_rlhf", "grpo",
                              "distill_logit", "distill_sequence"}:
        # Preference-based objectives (dpo/ipo/kto/orpo/ppo_rlhf/grpo) genuinely need paired
        # preference data we don't synthesize here — honest objective stub, not silent training.
        # sft/distill_* only land here if no corpus was loaded.
        print(f"[INFO] {resolved_method} is a training objective method.")
        print("[INFO] Attach a preference/instruction dataset via --corpus for full training.")
    else:
        print("[WARN] No corpus or operators. Nothing to train.")
        return 1

    # Save adapter (PEFT delta-operator runs only; alignment runs saved their full model above)
    if isinstance(operators, dict) and operators:
        save_adapter(resolved_method, operators, output_dir, args)

    # Final bench
    if not getattr(args, "no_bench", False):
        run_final_bench(output_dir)

    print(f"[SUCCESS] PEFT run complete. Adapter saved to: {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
