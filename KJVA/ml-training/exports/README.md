# Export Workspace

This directory stores reusable model bundles produced after training and
validation.

Expected generated bundle IDs:

- `kjv_bpe_v1_20m/`
- `kjv_byte_v1_20m/`
- `kjv_tokenless_v1_active` symlink, created only after publish gates pass.

Bundle contents should include weights, config, tokenizer or byte metadata,
retrieval assets, manifest, training recipe, validation report, and minimal
runtime scripts. Large weights remain ignored by Git.
