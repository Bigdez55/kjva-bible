# Omni-PEFT++ Formal Property Specs (§11.2 step 17)

Each property is a pure predicate in `properties.py`, enforced by `tests/test_v2_modules.py`.

| ID | Property | Predicate | Enforced by |
|----|----------|-----------|-------------|
| P1 | AdapterIR flatten→unflatten is lossless (content hash preserved) | `prop_ir_roundtrip` | test_v2_modules::test_ir_roundtrip |
| P2 | Content hash is stable across an independent copy | `prop_hash_stable` | test_v2_modules::test_hash_stable |
| P3 | Additive algebra is invertible: `subtract(compose(a,b),b) ≈ a` | `prop_compose_invertible` | test_v2_modules::test_algebra |
| P4 | Compressing an already-rank-r tensor to r is near-lossless | `prop_compress_preserves_lowrank` | test_v2_modules::test_compress |
| P5 | Route replay is deterministic: identical (seed,inputs) ⇒ identical plan | `prop_replay_deterministic` | test_v2_modules::test_determinism |
| P6 | Genome v1↔v2 is lossless on v1 fields (registry.load stays valid) | `prop_genome_v1_lossless` | test_v2_modules::test_genome |

All predicates are framework-neutral (numpy/stdlib) and run without torch or mlx.
