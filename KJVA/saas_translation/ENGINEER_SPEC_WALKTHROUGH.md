# Engineer Walkthrough

The Tokenless model pattern is intentionally small:

1. Load a local export.
2. Retrieve relevant corpus passages.
3. Assemble the cognitive prompt.
4. Generate with the model.
5. Apply governance checks before and after generation.
6. Run Heptagon metadata evaluation.
7. Append a signal record.
8. Return a UI-friendly response envelope.

When reproducing the model in another project, copy the wiring pattern and then
replace project identity, corpus, model export, and deployment policy locally.
