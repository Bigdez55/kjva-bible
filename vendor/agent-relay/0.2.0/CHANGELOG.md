# Changelog

## 0.2.0 — 2026-09-28

- Implemented installed MCP stdio adapter with durable provider-neutral sessions,
  canonical identity, delivered-context acknowledgments and reset fencing (G24).
- Added optional mTLS remote-worker transport to one authority; certificate/grant
  binding, no remote owner operations, no offline authority and conservative
  post-send uncertainty. Added real dropped-reply/reconnection tests (G27).
- Added actual 0.1.0/schema-1 staged migration, fresh credentials, preserved event
  bytes and controlled preactivation rollback, with interrupted-copy tests (G30).
- Added immutable candidate/test/runner-bound gate policy and expiring explicit
  boundary-review decisions. Failed tests and reviewed exceptions cannot become PASS.
- Fixed source-mode test runner subprocess imports. Added post-run identity checks
  and collection of unraisable cleanup errors. Retained original regression suite.
- Separated event schema 1 from store schema 2 so historical hashes never change.
- Added peer/session revocation/closure to reserved recovery journal capacity.

## 0.1.0 — prior baseline

Original deterministic local controller with recorder, action/evidence gates,
installed recovery self-test and 111 shipped tests. Exact wheel/tests retained
under compat/; metadata and reports are historical, not current-candidate proof.
