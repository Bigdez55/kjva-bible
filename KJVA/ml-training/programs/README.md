# Tokenless Omni Training Program

The omni program is the registry and controller layer for every training method
this repo can reason about. It does not pretend that every method is executable
before prerequisites exist. Instead, each method is registered with:

- required artifacts
- produced artifacts
- implementation status
- runner path when executable
- compatibility gates

The current concrete stack is `kjv_tokenless_master_stack`, which delegates the
implemented KJV corpus, byte pretraining, BPE baseline, retrieval validation,
export, and publish stages to `ml-training/scripts/run_retrain.py`.

Core commands:

```bash
python3 ml-training/scripts/omni_training_program.py validate
python3 ml-training/scripts/omni_training_program.py matrix
python3 ml-training/scripts/omni_training_program.py plan
python3 ml-training/scripts/omni_training_program.py export-corpus \
  --out "ml-training/corpus/programs/omni_training_programs.jsonl"
python3 ml-training/scripts/omni_training_program.py run --dry-run
```

Run the concrete KJV delegated pipeline:

```bash
python3 ml-training/scripts/omni_training_program.py run
```

PEFT, alignment, distillation, and learned retrieval methods are registered as
`extension_spec` until a published base checkpoint exists and their concrete
trainer adapters are implemented.
