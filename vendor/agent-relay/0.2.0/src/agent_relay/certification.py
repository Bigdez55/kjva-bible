"""Candidate-bound gate evaluation with explicit, expiring reviewer decisions.

A passing test's gate tag is coverage, not full certification. The committed gate
policy lists required test IDs and remaining review boundaries. Failed/missing
tests are never converted to PASS by an exception. An exception accepts only a
named remaining boundary, is bound to exact evidence/policy/candidate bytes, and
is reported as EXCEPTED, never as a passing original guarantee.

Reports and local review HMACs are not publisher signatures or proof that the
holder of a same-UID review key is a particular human. Keep that key out of worker
processes and use an external CI/reviewer boundary for stronger assurance.
"""
from __future__ import annotations

from importlib.resources import files
import hashlib
import hmac
import json
from pathlib import Path
import re
import time
from .codec import canonical, digest, object_digest, strict_loads, text
from .errors import RelayError, require
from .network import private_file


def runtime_identity() -> tuple[str, list[dict]]:
    root = Path(str(files("agent_relay")))
    entries = []
    for path in sorted(root.rglob("*")):
        if path.is_file() and "__pycache__" not in path.parts and path.suffix not in (".pyc", ".pyo"):
            entries.append({"path": path.relative_to(root).as_posix(), "sha256": digest(path.read_bytes())})
    return object_digest(entries), entries


def installed_policy() -> dict:
    return strict_loads(files("agent_relay").joinpath("data/gate_policy.json").read_bytes())


def load(path: Path, limit=16*1024*1024) -> tuple[dict, str]:
    require(path.is_file() and path.stat().st_size <= limit, "EVIDENCE_FILE", "missing/oversized evidence file")
    raw = path.read_bytes()
    data = strict_loads(raw)
    require(type(data) is dict, "EVIDENCE_SCHEMA", "evidence must be an object")
    return data, digest(raw)


def review_key(path: Path) -> bytes:
    private_file(path)
    key = path.read_bytes()
    require(32 <= len(key) <= 4096, "REVIEW_KEY", "review key must contain 32..4096 bytes")
    return key


def sign_review(review: dict, key: bytes) -> dict:
    required = {"gate_id", "runtime_sha256", "policy_sha256", "evidence_sha256", "reviewer", "reason", "expires_at", "decision"}
    require(set(review) == required and review["decision"] == "ACCEPT_REMAINING_BOUNDARY", "REVIEW_SCHEMA", "invalid reviewer decision")
    text(review["reviewer"], "reviewer", 256)
    reason = text(review["reason"], "reason", 8192)
    require(reason.strip().upper() not in {"TODO", "TBD", "APPROVED", "PASS"}, "REVIEW_REASON", "describe the exact boundary and consequence")
    require(type(review["expires_at"]) in (int, float), "REVIEW_SCHEMA", "expiry required")
    return {"review": review, "hmac_sha256": hmac.new(key, canonical(review), hashlib.sha256).hexdigest()}


def evaluate(report_path: Path, policy_path: Path, decisions_path: Path | None = None,
             key_path: Path | None = None, *, now: float | None = None) -> dict:
    now = time.time() if now is None else now
    report, report_hash = load(report_path)
    policy, policy_hash = load(policy_path)
    current, _ = runtime_identity()
    require(policy == installed_policy(), "GATE_POLICY_CHANGED", "policy must match the immutable installed release policy; do not weaken gates to manufacture readiness")
    original_raw = files("agent_relay").joinpath("data/original_gates.json").read_bytes()
    original = strict_loads(original_raw)
    ids = {g["id"] for g in original["gates"]}
    require(policy.get("original_contract_sha256") == digest(original_raw), "CONTRACT_CHANGED", "policy must retain the exact original contract")
    require(type(policy.get("gates")) is list, "GATE_POLICY", "policy gates required")
    gates = policy["gates"]
    require(len(gates) == len(ids) and {g.get("id") for g in gates} == ids,
            "GATE_POLICY", "all 46 original IDs must be present exactly once")
    require(report.get("runtime_sha256") == current and report.get("source_sha256") == current,
            "CANDIDATE_MISMATCH", "results do not apply to the current installed runtime")
    require(report.get("runtime_after_sha256") == current, "CANDIDATE_MISMATCH", "runtime changed during tests or no after-run identity exists")
    require(report.get("tests_after_sha256") == report.get("tests_sha256") and bool(report.get("tests_sha256")),
            "VERIFIER_CHANGED", "test bytes changed during the run")
    require(report.get("tests_sha256") == policy.get("tests_sha256"), "VERIFIER_CHANGED", "executed tests differ from the release-pinned verifier tree")
    require(report.get("runner_sha256") == policy.get("runner_sha256") and report.get("runner_after_sha256") == report.get("runner_sha256") and bool(report.get("runner_sha256")),
            "VERIFIER_CHANGED", "runner is missing, changed or not the release-pinned runner")
    require(report.get("environment", {}).get("installed_mode") is True,
            "NOT_INSTALLED_EVIDENCE", "source-only execution cannot certify an installed release")
    require(type(report.get("records")) is list and bool(report["records"]), "EMPTY_EVIDENCE", "no executed tests")
    records = report["records"]
    require(len({r.get("test") for r in records}) == len(records), "DUPLICATE_TEST", "duplicate test IDs do not increase evidence")
    by_test = {r["test"]: r for r in records}
    require(report.get("tests_run") == len(records), "EVIDENCE_COUNTS", "test counts inconsistent")
    all_tests_ok = report.get("ok") is True and not report.get("unraisable_errors",[]) and all(r.get("status") == "PASS" for r in records)
    approvals = {}
    if decisions_path is not None:
        require(key_path is not None, "REVIEW_KEY", "reviewed exceptions require an external review key")
        decisions, _ = load(decisions_path, 1024*1024)
        require(type(decisions.get("decisions")) is list, "REVIEW_SCHEMA", "decisions list required")
        key = review_key(key_path)
        for signed in decisions["decisions"]:
            require(type(signed) is dict and set(signed) == {"review", "hmac_sha256"}, "REVIEW_SCHEMA", "signed review required")
            r = signed["review"]
            expected = sign_review(r, key)["hmac_sha256"]
            require(type(signed["hmac_sha256"]) is str and hmac.compare_digest(expected, signed["hmac_sha256"]),
                    "REVIEW_SIGNATURE", "review key signature mismatch")
            require(r["runtime_sha256"] == current and r["policy_sha256"] == policy_hash and r["evidence_sha256"] == report_hash,
                    "REVIEW_BINDING", "review cannot be reused for a different candidate, policy or evidence")
            require(r["expires_at"] > now, "REVIEW_EXPIRED", "review decision expired")
            require(r["gate_id"] in ids and r["gate_id"] not in approvals, "REVIEW_SCHEMA", "unknown/duplicate reviewed gate")
            approvals[r["gate_id"]] = r
    rows = []
    for gate in gates:
        required_tests = gate.get("required_tests")
        require(type(required_tests) is list and bool(required_tests) and len(set(required_tests)) == len(required_tests),
                "GATE_POLICY", "every gate needs explicit distinct test IDs, not tag-count certification")
        missing = [t for t in required_tests if t not in by_test or by_test[t].get("status") != "PASS" or gate["id"] not in by_test[t].get("gate_ids", [])]
        needs_review = gate.get("remaining_boundary", "")
        require(type(needs_review) is str, "GATE_POLICY", "boundary must be explicit text")
        status = "TESTS_MISSING_OR_FAILED" if missing else "NEEDS_REVIEW" if needs_review else "PASS_IN_DECLARED_PROFILE"
        decision = approvals.get(gate["id"])
        if status == "NEEDS_REVIEW" and decision:
            status = "EXCEPTED_REMAINING_BOUNDARY"
        rows.append({"id": gate["id"], "status": status, "required_tests": required_tests,
                     "missing_or_failed": missing, "remaining_boundary": needs_review,
                     "reviewer_decision": decision})
    ready = all_tests_ok and all(r["status"] in {"PASS_IN_DECLARED_PROFILE", "EXCEPTED_REMAINING_BOUNDARY"} for r in rows)
    return {"ready": ready, "profile": policy.get("profile"), "runtime_sha256": current,
            "policy_sha256": policy_hash, "evidence_sha256": report_hash, "original_contract_sha256": digest(original_raw),
            "all_tests_ok": all_tests_ok, "gates": rows,
            "reviewed_exception_count": sum(r["status"] == "EXCEPTED_REMAINING_BOUNDARY" for r in rows),
            "full_original_certification": False,  # local scoped evidence does not become unqualified production proof
            "assurance": "CANDIDATE_BOUND_LOCAL_EVIDENCE_WITH_EXPLICIT_REVIEW_NOT_PUBLISHER_ATTESTATION"}


def unsigned_reviews(evaluation: dict, reviewer: str, ttl: float = 86400) -> dict:
    require(0 < ttl <= 86400*30, "REVIEW_TTL", "review lifetime must be 0..30 days")
    return {"decisions": [{"gate_id": g["id"], "runtime_sha256": evaluation["runtime_sha256"],
            "policy_sha256": evaluation["policy_sha256"], "evidence_sha256": evaluation["evidence_sha256"],
            "reviewer": reviewer, "reason": "TODO", "expires_at": time.time()+ttl, "decision": "ACCEPT_REMAINING_BOUNDARY"}
            for g in evaluation["gates"] if g["status"] == "NEEDS_REVIEW"]}
