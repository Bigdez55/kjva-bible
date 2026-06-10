# Export Workspace

This directory stores reusable model bundles produced after training and
validation.

Expected generated bundle IDs (consuming project picks its own naming):

- `bpe_v1_20m/`
- `byte_v1_20m/`
- `<base>_active` symlink, created only after publish gates pass.

Bundle contents should include weights, config, tokenizer or byte-vocab
metadata, optional retrieval assets, manifest, training recipe, validation
report, and minimal runtime scripts. Large weights remain ignored by Git.
