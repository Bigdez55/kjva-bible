"""
omni_scribe.py — Omni-PEFT Scribe Alignment training regimen.

Target behavior (owner-directed, 2026-06-09): a Bible + Apocrypha *scribe
assistant* with constitutional governance — NOT a governance adapter that
merely preserves scripture.

Three cooperating layers (only layer 3 is trained here):
  1. Frozen canonical base   — scripture-distribution fluency (retained).
  2. Retrieval index/server  — exact verse text, topical finding, citation
                               validation, Apocrypha. ALREADY built + tested
                               (grounding gate). The verbatim authority.
  3. Omni-PEFT scribe adapter — the BEHAVIORAL overlay trained here: when to
                               retrieve vs. speak, abstain on invalid citations,
                               reference-first formatting, governance/authority,
                               reverent style, scripture fluency.

Doctrine (unchanged from OMNI_PEFT_DOCTRINE.md): ONE fused genome, ONE forward
pass, ONE loss, ONE backward pass, ONE artifact. v2 changes ONLY data selection
(four weighted pools) and per-epoch evaluation (held-out scripture BPB retention
gate + early-stop). The injection / value_and_grad plumbing is untouched.

Pool mix (owner-set 2026-06-09):
  45% scripture mastery / retention  (raw clean-corpus scripture, all canon sections)
  25% grounding / citation / abstention
  20% constitutional governance
  10% scribe teaching style

Exact verse recall is DELEGATED to retrieval; the adapter is trained to ROUTE,
not to memorize verses (a 1.2M-param byte adapter cannot hold 36,822 verses
verbatim — training it to try would confabulate).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import mlx.core as mx
import mlx.nn as nn
import mlx.optimizers as optim
import numpy as np

# peft package imports require ml-training on sys.path (see CLAUDE.md)
_ML_TRAINING = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ML_TRAINING))
sys.path.insert(0, str(Path(__file__).resolve().parent))


# ---------------------------------------------------------------------------
# Pool definitions
# ---------------------------------------------------------------------------

POOL_WEIGHTS = {
    "retention": 0.45,
    "grounding": 0.25,
    "governance": 0.20,
    "scribe": 0.10,
}

# category -> training pool (audited categories + new scribe categories)
CATEGORY_TO_POOL = {
    # governance / constitutional / authority
    "absolute_covenant_immutability": "governance",
    "authentication_required": "governance",
    "authority_transparency": "governance",
    "canonical_weight_authority": "governance",
    "creator_sovereign_authority": "governance",
    "deployment_owner_authority": "governance",
    "false_witness": "governance",
    "harm_prevention": "governance",
    "identity_integrity": "governance",
    "manipulation": "governance",
    "oppression_or_exploitation": "governance",
    "privacy_violation": "governance",
    "proportional_response": "governance",
    "theft_or_fraud": "governance",
    "user_tier_escalation_rejection": "governance",
    # grounding / citation / abstention / retrieval-routing
    "calibration_uncertainty": "grounding",
    "capability_tier_boundary": "grounding",
    "cross_reference_routing": "grounding",
    "invalid_citation_abstention": "grounding",
    "raw_generation_fallback_discipline": "grounding",
    "retrieval_first_scripture_response": "grounding",
    "scripture_grounded_answer": "grounding",
    "topical_reference_finding": "grounding",
    # scribe teaching style
    "benign_governance_inquiry": "scribe",
    "benign_theological": "scribe",
    "capability_self_description": "scribe",
    "in_scope_response": "scribe",
    "scribe_teaching_style": "scribe",
}

# canon section -> book codes (for held-out coverage reporting)
CANON_SECTIONS = {
    "torah": ("GEN", "EXO", "LEV", "NUM", "DEU"),
    "prophets": ("ISA", "JER", "EZE", "DAN", "HOS", "JOE", "AMO", "OBA",
                 "JON", "MIC", "NAH", "HAB", "ZEP", "HAG", "ZEC", "MAL"),
    "writings": ("PSA", "PRO", "JOB", "ECC", "SNG", "RUT", "LAM", "EST",
                 "EZR", "NEH", "1CH", "2CH"),
    "gospels": ("MAT", "MRK", "LUK", "JHN"),
    "epistles": ("ROM", "1CO", "2CO", "GAL", "EPH", "PHP", "COL", "1TH",
                 "2TH", "1TI", "2TI", "TIT", "PHM", "HEB", "JAS", "1PE",
                 "2PE", "1JN", "2JN", "3JN", "JUD"),
    "apocrypha": ("TOB", "JDT", "SIR", "WIS", "BAR", "1MA", "2MA", "BEL",
                  "SUS", "MAN", "1ES", "2ES", "S3Y", "ESG"),
}

LN2 = float(np.log(2.0))

# Byte-id offset reserved for special tokens (pad/bos/eos). The canonical base
# (vocab_size=259 = 256 bytes + 3 specials) encodes a raw byte b as id (b +
# BYTE_OFFSET). This MUST match the base's byte_vocab.json or every token is
# shifted and the model mispredicts confidently (BPB >> uniform). Read from
# byte_vocab.json when available; default 3.
BYTE_OFFSET = 3


def resolve_byte_offset(corpus_or_vocab: Path) -> int:
    """Find byte_offset from a sibling/own byte_vocab.json; fall back to 3."""
    candidates = []
    p = Path(corpus_or_vocab)
    if p.name == "byte_vocab.json":
        candidates.append(p)
    candidates += [p.parent / "byte_vocab.json",
                   p.parent.parent / "byte_vocab.json"]
    for c in candidates:
        try:
            if c.exists():
                v = json.loads(c.read_text())
                if isinstance(v, dict) and "byte_offset" in v:
                    return int(v["byte_offset"])
        except Exception:
            pass
    return BYTE_OFFSET


def _verse_section(line: str) -> str | None:
    """Map a verse line ('GEN 1:1 ...') to a canon section, or None."""
    code = line.split(" ", 1)[0].strip()
    for section, books in CANON_SECTIONS.items():
        if code in books:
            return section
    return None


# ---------------------------------------------------------------------------
# Tokenisation helpers (byte-level, matches load_corpus_tokens convention)
# ---------------------------------------------------------------------------

def _text_to_seq(text: str, max_len: int, byte_offset: int = BYTE_OFFSET) -> mx.array | None:
    """Encode text -> (b+byte_offset) byte ids, truncated to max_len+1. Need >=2 toks."""
    from byte_codec import encode_bytes
    toks = encode_bytes(text.encode("utf-8"), vocab_size=256 + byte_offset)
    if len(toks) < 2:
        return None
    toks = toks[: max_len + 1]
    return mx.array(toks)


def _text_to_windows(text: str, seq_len: int, byte_offset: int = BYTE_OFFSET) -> list[mx.array]:
    """Chunk a long text into non-overlapping (seq_len+1)-token windows."""
    from byte_codec import encode_bytes
    toks = encode_bytes(text.encode("utf-8"), vocab_size=256 + byte_offset)
    out: list[mx.array] = []
    for i in range(0, len(toks) - seq_len, seq_len):
        chunk = toks[i: i + seq_len + 1]
        if len(chunk) == seq_len + 1:
            out.append(mx.array(chunk))
    return out


def format_alignment_row(row: dict) -> str:
    """Render an audited 9-key alignment row into the [INST]/[IN]/[OUT] form."""
    return (
        f"[INST] {row['instruction']}\n"
        f"[IN] {row['input']}\n"
        f"[OUT] {row['expected_output']}\n"
    )


def format_alignment_row_split(row: dict) -> tuple[str, int]:
    """Return (full_text, out_start_byte_index).

    out_start = byte length of the '[INST] …\\n[IN] …\\n[OUT] ' prefix. With
    byte-level (1 byte == 1 token) encoding this is also the token index at which
    the [OUT] completion begins — used for completion-only loss masking so the
    adapter learns the RESPONSE, not the instruction/input surface text.
    """
    prefix = f"[INST] {row['instruction']}\n[IN] {row['input']}\n[OUT] "
    full = f"{prefix}{row['expected_output']}\n"
    return full, len(prefix.encode("utf-8"))


# ---------------------------------------------------------------------------
# Pool + held-out construction
# ---------------------------------------------------------------------------

def build_scribe_pools(
    clean_corpus: Path,
    programs_dir: Path,
    seq_len: int = 256,
    heldout_every: int = 90,
    byte_offset: int = BYTE_OFFSET,
) -> tuple[dict, dict, dict]:
    """
    Build the four training pools + a held-out scripture slice.

    Returns (pools, heldout, stats):
      pools:   {"retention": [seq...], "grounding": [...], "governance": [...],
                "scribe": [...]}
      heldout: {"all": [seq...], "<section>": [seq...]}  — NEVER trained
      stats:   diagnostics dict
    """
    # --- scripture: split verses into train (retention pool) vs held-out ---
    lines = [ln for ln in clean_corpus.read_text(encoding="utf-8").splitlines() if ln.strip()]

    heldout_lines: list[str] = []
    train_lines: list[str] = []
    for i, ln in enumerate(lines):
        if i % heldout_every == 0:
            heldout_lines.append(ln)
        else:
            train_lines.append(ln)

    retention_chunks = _text_to_windows("\n".join(train_lines), seq_len, byte_offset)

    # held-out per section + overall (each verse encoded independently so a
    # held-out verse never shares a window with a trained verse)
    heldout: dict[str, list[mx.array]] = {"all": []}
    heldout_section_counts: dict[str, int] = {}
    for ln in heldout_lines:
        seq = _text_to_seq(ln, seq_len, byte_offset)
        if seq is None:
            continue
        heldout["all"].append(seq)
        sec = _verse_section(ln)
        if sec:
            heldout.setdefault(sec, []).append(seq)
            heldout_section_counts[sec] = heldout_section_counts.get(sec, 0) + 1

    # --- alignment rows: bucket by category into grounding/governance/scribe ---
    # Each pool item is (seq, out_start): out_start is the token index at which
    # loss begins. Retention = full-sequence loss (out_start=1: model all of
    # scripture). Alignment = completion-only (out_start = end of [OUT] prefix).
    pools: dict[str, list[tuple]] = {
        "retention": [(c, 1) for c in retention_chunks],
        "grounding": [],
        "governance": [],
        "scribe": [],
    }
    pool_row_counts = {"grounding": 0, "governance": 0, "scribe": 0}
    skipped_no_out = 0
    unmapped: set[str] = set()

    align_files = sorted(programs_dir.glob("alignment_*_v1.jsonl"))
    for f in align_files:
        for raw in f.read_text(encoding="utf-8").splitlines():
            raw = raw.strip()
            if not raw:
                continue
            row = json.loads(raw)
            cat = row.get("category", "")
            pool = CATEGORY_TO_POOL.get(cat)
            if pool is None:
                unmapped.add(cat)
                pool = "scribe"  # safe catch-all
            full, out_start = format_alignment_row_split(row)
            seq = _text_to_seq(full, seq_len, byte_offset)
            if seq is None:
                continue
            # Need at least one [OUT] token inside the (possibly truncated) window.
            if out_start >= int(seq.shape[0]) - 1:
                skipped_no_out += 1
                continue
            pools[pool].append((seq, out_start))
            pool_row_counts[pool] += 1

    stats = {
        "scripture_lines_total": len(lines),
        "scripture_train_lines": len(train_lines),
        "heldout_verses": len(heldout["all"]),
        "heldout_section_counts": heldout_section_counts,
        "retention_chunks": len(retention_chunks),
        "grounding_rows": pool_row_counts["grounding"],
        "governance_rows": pool_row_counts["governance"],
        "scribe_rows": pool_row_counts["scribe"],
        "alignment_files": [f.name for f in align_files],
        "unmapped_categories": sorted(unmapped),
        "skipped_no_out_span": skipped_no_out,
        "seq_len": seq_len,
        "heldout_every": heldout_every,
        "byte_offset": byte_offset,
        "completion_only_masking": True,
    }
    return pools, heldout, stats


# ---------------------------------------------------------------------------
# BPB measurement (bits per byte; byte-level model => per-token CE == per-byte)
# ---------------------------------------------------------------------------

def compute_bpb(model, chunks: list[mx.array], max_eval: int = 400) -> float:
    """Mean cross-entropy (bits/byte) over up to max_eval held-out sequences."""
    if not chunks:
        return float("nan")
    total_nats = 0.0
    total_tok = 0
    for seq in chunks[:max_eval]:
        if seq.shape[0] < 2:
            continue
        tokens = seq[:-1].reshape(1, -1)
        targets = seq[1:].reshape(1, -1)
        logits = model(tokens)
        B, T, V = logits.shape
        ce = nn.losses.cross_entropy(logits.reshape(B * T, V), targets.reshape(B * T))
        total_nats += float(mx.sum(ce).item())
        total_tok += B * T
    if total_tok == 0:
        return float("nan")
    return (total_nats / total_tok) / LN2


# ---------------------------------------------------------------------------
# Pooled training loop
# ---------------------------------------------------------------------------

def run_omni_scribe_training(base_model, args, output_dir: Path) -> dict:
    """
    Omni-PEFT Scribe Alignment training.

    Single optimizer, single CE loss, all operators. Each step draws a pool by
    POOL_WEIGHTS then a random sequence from that pool. After each epoch, measure
    held-out scripture BPB; early-stop if it regresses beyond args.bpb_max_regress
    bits/byte vs the frozen-base baseline measured pre-injection.
    """
    from peft.base import AdaptationConstraints, HardwareBudget
    from peft.fingerprint import TaskFingerprinter, DataSize
    from peft.profiler import ModelProfiler
    from peft.compiler import PEFTCompiler
    from peft.omni_composite import OmniPEFTCompositeAdapter

    clean_corpus = Path(args.clean_corpus)
    programs_dir = Path(args.programs_dir)
    seq_len = min(getattr(args, "scribe_seq_len", 256), base_model.cfg.max_seq_len)
    # byte model: vocab = 256 bytes + n_special; byte_offset = n_special.
    byte_offset = int(base_model.cfg.vocab_size) - 256
    if byte_offset < 0:
        byte_offset = BYTE_OFFSET
    print(f"[scribe] byte_offset={byte_offset} (vocab_size={base_model.cfg.vocab_size})")

    pools, heldout, stats = build_scribe_pools(
        clean_corpus, programs_dir, seq_len=seq_len,
        heldout_every=getattr(args, "heldout_every", 90),
        byte_offset=byte_offset,
    )
    print("[scribe] pools built:")
    print(f"  retention chunks : {stats['retention_chunks']}")
    print(f"  grounding rows   : {stats['grounding_rows']}")
    print(f"  governance rows  : {stats['governance_rows']}")
    print(f"  scribe rows      : {stats['scribe_rows']}")
    print(f"  held-out verses  : {stats['heldout_verses']} "
          f"({stats['heldout_section_counts']})")
    if stats["unmapped_categories"]:
        print(f"  [WARN] unmapped categories -> scribe pool: {stats['unmapped_categories']}")

    # preflight: every section + apocrypha represented in held-out
    missing = [s for s in CANON_SECTIONS if s not in stats["heldout_section_counts"]]
    if missing:
        print(f"  [WARN] held-out missing canon sections: {missing}")
    if not any(p for k, p in pools.items() if k != "retention"):
        raise RuntimeError("No alignment rows loaded — check programs_dir.")

    # active pools (drop empties, renormalise weights)
    active = {k: v for k, v in pools.items() if v}
    weights = np.array([POOL_WEIGHTS[k] for k in active], dtype=np.float64)
    weights = weights / weights.sum()
    pool_names = list(active.keys())
    print(f"[scribe] active pools={pool_names} weights={[round(float(w),3) for w in weights]}")

    # --- baseline BPB on the FROZEN base, BEFORE injection ---
    base_model.freeze()
    baseline_bpb = compute_bpb(base_model, heldout["all"])
    baseline_sections = {
        s: compute_bpb(base_model, heldout[s])
        for s in CANON_SECTIONS if s in heldout
    }
    print(f"[scribe] baseline held-out BPB (frozen base, pre-injection): {baseline_bpb:.4f} bits/byte")

    # --- build + inject composite ---
    hardware = HardwareBudget(train_vram_mb=getattr(args, "train_vram_mb", 16000))
    constraints = AdaptationConstraints(hardware=hardware)
    cfg_dict = {
        "vocab_size": base_model.cfg.vocab_size,
        "n_layers": base_model.cfg.n_layers,
        "d_model": base_model.cfg.d_model,
        "d_ffn": base_model.cfg.d_ffn,
    }
    plasticity = ModelProfiler().profile(cfg_dict, constraints)
    fingerprint = TaskFingerprinter().fingerprint(
        task_desc="omni scribe alignment",
        domains=["scripture", "governance", "alignment"],
        data_size=DataSize.MEDIUM,
        hardware=hardware,
    )
    plan = PEFTCompiler().plan(plasticity, fingerprint, constraints)
    composite = OmniPEFTCompositeAdapter.from_plan(
        plan, base_model,
        enable_ia3=True, enable_bitfit=True, enable_prefix=True,
        prefix_n=getattr(args, "prompt_tokens", 8),
    )
    rollback = composite.inject_into(base_model)
    print(f"[scribe] composite: methods={composite._genome_methods}, "
          f"operators={composite._operator_count}, injected={len(rollback)}")

    # sanity invariant: post-injection BPB ~= baseline (operators init near-identity)
    post_inject_bpb = compute_bpb(base_model, heldout["all"])
    print(f"[scribe] post-injection BPB (epoch 0, should ~= baseline): {post_inject_bpb:.4f} "
          f"(delta {post_inject_bpb - baseline_bpb:+.4f})")

    # --- single-loss pooled training ---
    key_state = {"k": mx.random.key(0)}

    def _draw_seq():
        # choose pool by weight, then a (seq, out_start) within it (mx.random
        # with split keys so resume/determinism is stable)
        key_state["k"], kp, ks = mx.random.split(key_state["k"], num=3)
        pi = int(mx.random.categorical(mx.log(mx.array(weights.tolist())), key=kp).item())
        pool = active[pool_names[pi]]
        si = int(mx.random.randint(0, len(pool), shape=(), key=ks).item())
        return pool[si]

    def compute_loss():
        seq, out_start = _draw_seq()
        tokens = seq[:-1].reshape(1, -1)
        targets = seq[1:].reshape(1, -1)
        logits = base_model(tokens)
        B, T, V = logits.shape
        ce = nn.losses.cross_entropy(logits.reshape(B * T, V), targets.reshape(B * T))
        # Completion-only masking: target index j predicts seq[j+1]; keep loss
        # where j >= out_start-1 (the [OUT] span). Retention out_start=1 => all j.
        start = max(0, out_start - 1)
        mask = (mx.arange(T) >= start).astype(ce.dtype)
        denom = mx.maximum(mx.sum(mask), mx.array(1.0))
        return mx.sum(ce * mask) / denom

    loss_and_grad = nn.value_and_grad(base_model, compute_loss)
    optimizer = optim.Adam(learning_rate=args.lr)

    epochs = args.epochs
    steps_per_epoch = args.steps_per_epoch
    bpb_max_regress = getattr(args, "bpb_max_regress", 0.15)  # bits/byte

    print(f"[scribe] training: <= {epochs} epochs x {steps_per_epoch} steps, "
          f"early-stop if held-out BPB > baseline + {bpb_max_regress} bits/byte")

    epoch_log: list[dict] = []
    total_loss = 0.0
    total_steps = 0
    stopped_early = False
    best_bpb = post_inject_bpb

    for epoch in range(epochs):
        epoch_loss = 0.0
        for step in range(steps_per_epoch):
            loss_val, grads = loss_and_grad()
            optimizer.update(base_model, grads)
            mx.eval(base_model.parameters(), optimizer.state)
            sl = float(loss_val.item())
            epoch_loss += sl
            total_loss += sl
            total_steps += 1
            if step % max(1, steps_per_epoch // 5) == 0:
                print(f"  [scribe] epoch {epoch+1}/{epochs} step {step+1}/{steps_per_epoch} "
                      f"loss={epoch_loss/(step+1):.4f}")

        avg = epoch_loss / max(1, steps_per_epoch)
        ep_bpb = compute_bpb(base_model, heldout["all"])
        regress = ep_bpb - baseline_bpb
        best_bpb = min(best_bpb, ep_bpb)
        # Per-epoch checkpoint (Pareto selection: don't keep only the final).
        ckpt_path = ""
        if getattr(args, "save_every_epoch", True):
            ep_dir = output_dir / f"epoch_{epoch+1:02d}"
            ep_dir.mkdir(parents=True, exist_ok=True)
            ep_w = {k: np.array(v) for k, v in composite.extract_weights().items()}
            np.savez(str(ep_dir / "omni_adapter_weights.npz"), **ep_w)
            ckpt_path = str(ep_dir / "omni_adapter_weights.npz")

        rec = {
            "epoch": epoch + 1,
            "avg_loss": round(avg, 4),
            "heldout_bpb": round(ep_bpb, 4),
            "bpb_regress_vs_baseline": round(regress, 4),
            "checkpoint": ckpt_path,
        }
        epoch_log.append(rec)
        print(f"[scribe] epoch {epoch+1}: avg_loss={avg:.4f} "
              f"heldout_BPB={ep_bpb:.4f} (regress {regress:+.4f} bits/byte)")

        if regress > bpb_max_regress:
            print(f"[scribe] EARLY STOP — scripture retention regressed "
                  f"{regress:.4f} > {bpb_max_regress} bits/byte. Halting.")
            stopped_early = True
            break

    final_avg_loss = total_loss / max(1, total_steps)
    final_bpb = compute_bpb(base_model, heldout["all"])
    final_sections = {
        s: round(compute_bpb(base_model, heldout[s]), 4)
        for s in CANON_SECTIONS if s in heldout
    }

    # --- save artifact ---
    output_dir.mkdir(parents=True, exist_ok=True)
    weights_out = composite.extract_weights()
    np_weights = {k: np.array(v) for k, v in weights_out.items()}
    np.savez(str(output_dir / "omni_adapter_weights.npz"), **np_weights)

    base_sha = ""
    if args.base_checkpoint and Path(args.base_checkpoint).exists():
        import hashlib
        base_sha = hashlib.sha256(Path(args.base_checkpoint).read_bytes()).hexdigest()[:16]

    genome = composite.genome_dict(
        base_model_sha256=base_sha,
        final_avg_loss=round(final_avg_loss, 4),
        training_epochs=len(epoch_log),
    )
    genome["regimen"] = "omni_scribe_alignment_v2"
    genome["pool_weights"] = POOL_WEIGHTS
    (output_dir / "omni_adapter_genome.json").write_text(json.dumps(genome, indent=2))

    report = {
        "artifact_type": "omni_peft_scribe_adapter",
        "regimen": "omni_scribe_alignment_v2",
        "doctrine": "ml-training/peft/OMNI_PEFT_DOCTRINE.md",
        "target": "Bible+Apocrypha scribe assistant with constitutional governance",
        "retrieval_delegation": "exact verse text + topical finding served by retrieval index, not adapter weights",
        "base_checkpoint": str(args.base_checkpoint or ""),
        "clean_corpus": str(clean_corpus),
        "programs_dir": str(programs_dir),
        "pool_weights": POOL_WEIGHTS,
        "pool_stats": stats,
        "enabled_methods": composite._genome_methods,
        "operator_count": composite._operator_count,
        "epochs_planned": epochs,
        "epochs_run": len(epoch_log),
        "stopped_early": stopped_early,
        "steps_per_epoch": steps_per_epoch,
        "baseline_heldout_bpb": round(baseline_bpb, 4),
        "baseline_section_bpb": {k: round(v, 4) for k, v in baseline_sections.items()},
        "post_injection_bpb": round(post_inject_bpb, 4),
        "final_heldout_bpb": round(final_bpb, 4),
        "best_heldout_bpb": round(best_bpb, 4),
        "final_bpb_regress_vs_baseline": round(final_bpb - baseline_bpb, 4),
        "bpb_max_regress_threshold": bpb_max_regress,
        "final_section_bpb": final_sections,
        "epoch_log": epoch_log,
        "final_avg_loss": round(final_avg_loss, 4),
        "is_tournament": False,
        "tournament_winner": None,
        "canonical_promoted": False,
    }

    # Pareto recommendation: among epochs whose alignment loss is within 15% of
    # the best (i.e. behavior is well-learned), pick the one with the LOWEST
    # held-out BPB regression (best scripture retention). This is the knee.
    if epoch_log:
        best_align = min(e["avg_loss"] for e in epoch_log)
        well_learned = [e for e in epoch_log if e["avg_loss"] <= best_align * 1.15]
        knee = min(well_learned, key=lambda e: e["bpb_regress_vs_baseline"])
        report["pareto_recommendation"] = {
            "epoch": knee["epoch"],
            "rationale": "lowest held-out BPB regression among well-learned epochs "
                         "(alignment loss within 15% of best)",
            "avg_loss": knee["avg_loss"],
            "heldout_bpb": knee["heldout_bpb"],
            "bpb_regress_vs_baseline": knee["bpb_regress_vs_baseline"],
            "checkpoint": knee["checkpoint"],
        }

    (output_dir / "omni_adapter_manifest.json").write_text(json.dumps(report, indent=2))
    print(f"[scribe] saved adapter ({len(np_weights)} tensors) + genome + manifest -> {output_dir}")
    print(f"[scribe] baseline BPB {baseline_bpb:.4f} -> final BPB {final_bpb:.4f} "
          f"(regress {final_bpb - baseline_bpb:+.4f} bits/byte)")
    return report
