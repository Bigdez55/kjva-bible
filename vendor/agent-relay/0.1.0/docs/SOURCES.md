# Input and technical reference register

Source design basis: user-provided `AGENT_RELAY_REVIEW_v2.zip` and
`AGENT_RELAY_RECONCILIATION_2026-09-27.zip`, especially the unchanged 46 contracts copied into
`contracts/ORIGINAL_G01_G46.json`. Original audited standalone source/test suite and the current live
workspace runtime were not supplied as executable implementation inputs. This is a new separate
implementation, not a claim that those source lineages were patched.

Primary technical references checked during implementation (2026-09-28):

- SQLite WAL documentation and WAL-reset bug/fix: https://www.sqlite.org/wal.html
- SQLite 3.51.3 release: https://www.sqlite.org/releaselog/3_51_3.html
- SQLite PRAGMA durability settings: https://www.sqlite.org/pragma.html
- Python sqlite3 connection lifetime: https://docs.python.org/3.13/library/sqlite3.html

The implementation accepts the documented fixed branches 3.51.3+, 3.50.7+ on 3.50, and 3.44.6+
on 3.44. Custom backports with different version numbers are conservatively refused for WAL; use
rollback mode or audit/update the allowlist rather than disabling the check. A version match is a
preflight policy, not independent attestation of a malicious or modified library binary.

Compression uses stdlib zlib and SHA-256 identities. No performance or hardware guarantee is inferred
from the source documents' unrelated brain/model scaling projections.
