# Training Signal Schema

Future runtime feedback may append one JSON object per line to
`$TOKENLESS_HOME/signals/YYYY-MM-DD.jsonl`. Signal capture is not part of the
v1 automatic training path.

## Fields

```json
{
  "id": "uuid-v4",
  "ts": "ISO-8601 UTC timestamp",
  "session_id": "opaque session id from server.py",
  "prompt_hash": "sha256(prompt_utf8)",
  "response_hash": "sha256(response_utf8)",
  "cycle_result": {
    "confidence": 0.0,
    "invariants_passed": [],
    "invariants_violated": [],
    "l5_eval_score": 0.0,
    "l6_sampler": {"temperature": 0.7, "top_p": 0.9},
    "trace_digest": "sha256 of cycle trace"
  },
  "policy": {
    "hard_stops_triggered": [],
    "soft_warnings": []
  },
  "retrieval_grounding": {
    "corpus_refs": [],
    "drift_score": 0.0
  },
  "user_signal": {
    "rating": null,
    "edited": false,
    "abandoned": false
  },
  "adapter_active": null,
  "latency_ms": 0
}
```

## Training inclusion criteria

A signal is eligible for training **only if**:
- `policy.hard_stops_triggered == []`
- `cycle_result.confidence >= 0.5`
- `user_signal.abandoned == False`

## Storage

- JSONL files: daily rotation, gzip after 24h, 90-day retention.
- `signals/index.db` SQLite: `(id, ts, confidence, hard_stop_count, file_offset)`
  for fast hold-out sampling.

## Identity preservation

Raw prompts and raw responses are not stored here, only their sha256 hashes.
Semantic signal is carried by `retrieval_grounding.corpus_refs`,
`cycle_result`, and `policy` fields.
