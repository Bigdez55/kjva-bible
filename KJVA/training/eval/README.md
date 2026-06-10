# Evaluation Workspace

This directory stores validation reports for training runs.

Each run's full benchmark is written by `ckpt_bench.run_final_bench` to
`eval/<run_id>/benchmark_final.json`. Consuming projects can add their own
domain validators (retrieval gates, citation correctness, etc.) and write
their reports here using a stable naming scheme such as
`<run_id>.eval.json` or `<gate>_report.json`.
