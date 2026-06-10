"""
eval_scribe_v2.py — Omni-PEFT Scribe Alignment v2 runtime evaluation.

Runs the held-out BEHAVIORAL probes (never trained) through base vs. base+adapter
with the correct byte offset, scores each probe's pass_signals / must_not, and
reads the training manifest for BPB-retention evidence. Produces an honest
generalization verdict — measures behavior the adapter never saw, not memorized
training strings.

Usage:
  python3 eval_scribe_v2.py \
    --adapter "models v7/training/gguf/archive/adapters/alignment_omnipeft_scribe_v2" \
    --base-checkpoint "../kjva-bible/KJVA/training/weights.safetensors" \
    --model-config "../kjva-bible/KJVA/training/model_config.json" \
    --probes "models v7/training/corpus/programs/heldout_behavioral_probes_v1.jsonl"
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import mlx.core as mx
import numpy as np

_ML_TRAINING = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ML_TRAINING))
sys.path.insert(0, str(Path(__file__).resolve().parent))


def _default_clean_corpus() -> str:
    """Resolve the clean corpus across layouts: substrate nested as 'models v7/'
    (upstream source) vs deployed flat as the KJVA project root."""
    repo_root = _ML_TRAINING.parent
    rel = "training/corpus/eng_kjv_clean_v1/corpus.txt"
    for base in (repo_root / "models v7", repo_root):
        cand = base / rel
        if cand.exists():
            return str(cand)
    return str(repo_root / rel)


def _encode(text: str, off: int) -> mx.array:
    return mx.array([[b + off for b in text.encode("utf-8")]])


def _decode(ids: list[int], off: int) -> str:
    return bytes([t - off for t in ids if off <= t < off + 256]).decode("utf-8", "replace")


def greedy(model, prompt: str, off: int, n: int = 140) -> str:
    toks = _encode(prompt, off)
    for _ in range(n):
        logits = model(toks)
        nxt = int(mx.argmax(logits[0, -1]).item())
        toks = mx.concatenate([toks, mx.array([[nxt]])], axis=1)
    full = _decode(toks[0].tolist(), off)
    return full[len(prompt):]  # continuation only


def build_base(base_ckpt: str, model_cfg: str):
    from model import ModelConfig, TokenlessLM
    mc = json.load(open(model_cfg))
    cfg = ModelConfig(
        vocab_size=mc["vocab_size"], n_layers=mc["n_layers"], n_heads=mc["n_heads"],
        d_model=mc["d_model"], d_ffn=mc["d_ffn"], max_seq_len=mc["max_seq_len"],
        rope_base=float(mc["rope_base"]), tie_embeddings=bool(mc["tie_embeddings"]),
    )
    m = TokenlessLM(cfg)
    w = mx.load(base_ckpt)
    m.load_weights(list(w.items()))
    m.freeze()
    return m, cfg


def load_adapter_into(base_model, adapter_dir: Path):
    """Rebuild the composite (same compiler plan), load npz weights, inject."""
    from mlx.utils import tree_unflatten, tree_flatten
    from peft.base import AdaptationConstraints, HardwareBudget
    from peft.fingerprint import TaskFingerprinter, DataSize
    from peft.profiler import ModelProfiler
    from peft.compiler import PEFTCompiler
    from peft.omni_composite import OmniPEFTCompositeAdapter

    hardware = HardwareBudget(train_vram_mb=16000)
    constraints = AdaptationConstraints(hardware=hardware)
    cfg_dict = {
        "vocab_size": base_model.cfg.vocab_size, "n_layers": base_model.cfg.n_layers,
        "d_model": base_model.cfg.d_model, "d_ffn": base_model.cfg.d_ffn,
    }
    plasticity = ModelProfiler().profile(cfg_dict, constraints)
    fingerprint = TaskFingerprinter().fingerprint(
        task_desc="omni scribe alignment", domains=["scripture", "governance", "alignment"],
        data_size=DataSize.MEDIUM, hardware=hardware,
    )
    plan = PEFTCompiler().plan(plasticity, fingerprint, constraints)

    npz = np.load(str(adapter_dir / "omni_adapter_weights.npz"))
    # Recover prefix_n from the saved prefix tensor (shape n_layers x n_prefix x d_model)
    # so the eval composite is STRUCTURALLY identical to the trained one.
    prefix_n = 8
    if "prefix_tuning.prefix_val" in npz.files:
        prefix_n = int(npz["prefix_tuning.prefix_val"].shape[1])
    composite = OmniPEFTCompositeAdapter.from_plan(
        plan, base_model, enable_ia3=True, enable_bitfit=True, enable_prefix=True,
        prefix_n=prefix_n)

    # Strict load-fidelity check: every saved key must exist in the composite tree
    # with a matching shape (composite.update is lenient and would silently skip).
    flat = {k: v for k, v in tree_flatten(composite.parameters())}
    mismatched, missing = [], []
    for k in npz.files:
        if k not in flat:
            missing.append(k)
        elif tuple(flat[k].shape) != tuple(npz[k].shape):
            mismatched.append((k, tuple(flat[k].shape), tuple(npz[k].shape)))
    if missing or mismatched:
        print(f"[eval][WARN] load fidelity: prefix_n={prefix_n} missing={missing[:3]} "
              f"mismatched={mismatched[:3]}")

    items = [(k, mx.array(npz[k])) for k in npz.files]
    composite.update(tree_unflatten(items))
    mx.eval(composite.parameters())
    injected = composite.inject_into(base_model)
    return composite, len(injected), len(items), prefix_n, len(missing) + len(mismatched)


def score_probe(probe: dict, output: str) -> dict:
    low = output.lower()
    hit = [s for s in probe.get("pass_signals", []) if s.lower() in low]
    violated = [s for s in probe.get("must_not", []) if s.lower() in low]
    # pass = at least one pass-signal present AND no must_not violated.
    # must_not strings are descriptive (hard to string-match), so treat them as
    # advisory unless an exact phrase appears; the human reads the transcript.
    passed = len(hit) > 0 and len(violated) == 0
    return {"pass_signals_hit": hit, "must_not_hit": violated, "auto_pass": passed}


PROMPT_TMPL = "[INST] Respond as a grounded scripture scribe.\n[IN] {input}\n[OUT] "


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--adapter", required=True)
    ap.add_argument("--base-checkpoint", required=True)
    ap.add_argument("--model-config", required=True)
    ap.add_argument("--probes", required=True)
    ap.add_argument("--clean-corpus",
                    default=_default_clean_corpus(),
                    help="Clean scripture corpus for the BPB fidelity recompute")
    ap.add_argument("--gen-bytes", type=int, default=140)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    adapter_dir = Path(args.adapter)
    off = json.load(open(args.model_config))["vocab_size"] - 256
    probes = [json.loads(l) for l in Path(args.probes).read_text().splitlines() if l.strip()]
    print(f"[eval] byte_offset={off} | probes={len(probes)}")

    # base-only outputs
    base, cfg = build_base(args.base_checkpoint, args.model_config)
    base_out = {}
    for p in probes:
        base_out[p["probe_id"]] = greedy(base, PROMPT_TMPL.format(input=p["input"]), off, args.gen_bytes)

    # base+adapter outputs (rebuild fresh base so injection is clean)
    base2, _ = build_base(args.base_checkpoint, args.model_config)
    composite, n_inj, n_w, prefix_n, n_bad = load_adapter_into(base2, adapter_dir)
    print(f"[eval] adapter: injected={n_inj} modules, loaded {n_w} tensors, "
          f"prefix_n={prefix_n}, load_mismatches={n_bad}")

    # DISCRIMINATING FIDELITY CHECK: recompute held-out BPB on the RELOADED model
    # and confirm it matches the epoch-15 training number. If it diverges, the
    # behavioral eval measured a mis-loaded adapter and the verdict is premature.
    import omni_scribe as _osc
    _off = base2.cfg.vocab_size - 256
    _, _heldout, _ = _osc.build_scribe_pools(
        Path(args.clean_corpus), Path(args.probes).parent,
        seq_len=256, heldout_every=90, byte_offset=_off)
    reload_bpb = _osc.compute_bpb(base2, _heldout["all"])
    print(f"[eval] reloaded-adapter held-out BPB={reload_bpb:.4f} "
          f"(training final={json.loads((adapter_dir/'omni_adapter_manifest.json').read_text()).get('final_heldout_bpb')})")

    adapt_out = {}
    for p in probes:
        adapt_out[p["probe_id"]] = greedy(base2, PROMPT_TMPL.format(input=p["input"]), off, args.gen_bytes)

    # score
    results = []
    n_changed = n_pass = 0
    for p in probes:
        pid = p["probe_id"]
        sc = score_probe(p, adapt_out[pid])
        changed = base_out[pid] != adapt_out[pid]
        n_changed += int(changed)
        n_pass += int(sc["auto_pass"])
        results.append({
            "probe_id": pid, "axis": p["axis"], "pool": p.get("pool"),
            "input": p["input"], "changed_vs_base": changed,
            **sc,
            "base_output": base_out[pid][:200],
            "adapter_output": adapt_out[pid][:200],
        })

    manifest = {}
    mpath = adapter_dir / "omni_adapter_manifest.json"
    if mpath.exists():
        manifest = json.loads(mpath.read_text())

    report = {
        "adapter": str(adapter_dir),
        "byte_offset": off,
        "prefix_n": prefix_n,
        "load_mismatches": n_bad,
        "reloaded_adapter_heldout_bpb": round(reload_bpb, 4),
        "probes_total": len(probes),
        "probes_changed_vs_base": n_changed,
        "probes_auto_pass": n_pass,
        "bpb_baseline": manifest.get("baseline_heldout_bpb"),
        "bpb_final": manifest.get("final_heldout_bpb"),
        "bpb_best": manifest.get("best_heldout_bpb"),
        "bpb_regress": manifest.get("final_bpb_regress_vs_baseline"),
        "epochs_run": manifest.get("epochs_run"),
        "stopped_early": manifest.get("stopped_early"),
        "final_section_bpb": manifest.get("final_section_bpb"),
        "probe_results": results,
    }
    out_path = Path(args.out) if args.out else (adapter_dir / "PROBE_EVAL.json")
    out_path.write_text(json.dumps(report, indent=2))

    print(f"\n[eval] probes changed vs base : {n_changed}/{len(probes)}")
    print(f"[eval] probes auto-pass       : {n_pass}/{len(probes)}")
    print(f"[eval] BPB {report['bpb_baseline']} -> {report['bpb_final']} "
          f"(regress {report['bpb_regress']}), epochs={report['epochs_run']}, "
          f"early_stop={report['stopped_early']}")
    print(f"[eval] wrote {out_path}")
    for r in results:
        flag = "PASS" if r["auto_pass"] else ("CHG " if r["changed_vs_base"] else "FLAT")
        print(f"  [{flag}] {r['probe_id']} {r['axis']}: hit={r['pass_signals_hit']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
