# Tokenless Omni Training Program

The omni program is the registry and controller layer for every training method
this repo can reason about. It does not pretend that every method is executable
before prerequisites exist. Instead, each method is registered with:

- required artifacts
- produced artifacts
- implementation status
- runner path when executable
- compatibility gates

The substrate ships `omni_training_registry.json` populated with the
domain-agnostic PEFT / alignment / distillation / retrieval methods. A
consuming project adds its own concrete stack entry (corpus builder + byte
or BPE pretraining + retrieval validation + export + publish) and a matching
`<project>_omni_program.yaml` that delegates to its own orchestrator script.

Core commands:

```bash
python3 training/scripts/omni_training_program.py validate
python3 training/scripts/omni_training_program.py matrix
python3 training/scripts/omni_training_program.py plan
python3 training/scripts/omni_training_program.py export-corpus \
  --out "training/corpus/programs/omni_training_programs.jsonl"
python3 training/scripts/omni_training_program.py run --dry-run
```

By default `omni_training_program.py` looks for
`training/programs/default_omni_program.yaml`. Override with `--program`.

PEFT, alignment, distillation, and learned retrieval methods are registered as
`extension_spec` until a published base checkpoint exists and their concrete
trainer adapters are implemented.
