"""KJVA Constitutional Cognitive Runtime executor.

``backend`` is only the HTTP adapter.  This module bridges the adapter to the
five KJVA contract roots that own runtime behavior:

constitution -> governance -> heptagon -> ai/xmind -> soul_manager
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

from inference import get_engine

_REPO_ROOT = Path(__file__).resolve().parents[1]
_KJVA_ROOT = _REPO_ROOT / "KJVA"
_AGENT_SRC = _KJVA_ROOT / "ai" / "tokenless-agent" / "src"
for _path in (_REPO_ROOT, _KJVA_ROOT, _AGENT_SRC):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from agent import AgentConfig, HeptagonLayer, TokenlessAgentWithHeptagon  # noqa: E402
from KJVA.governance.covenant_enforcer import (  # noqa: E402
    CovenantEnforcer,
    EnforcementAction,
)
from KJVA.governance.gate_evaluators import create_default_gate_chain  # noqa: E402
from KJVA.governance.interceptors import GovernanceInterceptors  # noqa: E402
from KJVA.governance.runtime_outcome import DecisionOutcome  # noqa: E402
from KJVA.governance.storage_envelope import (  # noqa: E402
    Classification,
    RetentionClass,
    StorageEnvelope,
)
from KJVA.ai.xmind.kjva_byte_backend import XmindBackendError, XmindPolicyHalt  # noqa: E402
from KJVA.heptagon.attestation import AttestationEngine, AttestationStatus  # noqa: E402
from KJVA.heptagon.member_guard import MemberGuard  # noqa: E402
from KJVA.heptagon.registry import MEMBER_REGISTRY  # noqa: E402
from KJVA.heptagon.vacancy_matrix import VacancyMatrix  # noqa: E402
from KJVA.soul_manager.soul_manager import SoulManager  # noqa: E402

AGENT_ID = "kjva-bible"
CREATED_BY = "tokenless-kjva-bible"

CONSTITUTION_DOCS = {
    "identity_attestation": "identity_attestation_doctrine.md",
    "degraded_mode": "degraded_mode_matrix.md",
    "seat_protection": "seat_protection_doctrine.md",
    "member_reconstitution": "member_reconstitution_doctrine.md",
}


class KJVARuntimeError(RuntimeError):
    status_code = 500

    def __init__(self, outcome: DecisionOutcome) -> None:
        super().__init__(outcome.detail)
        self.outcome = outcome


class KJVARuntimeDenied(KJVARuntimeError):
    status_code = 403


class KJVACovenantDenied(KJVARuntimeDenied):
    status_code = 422


class KJVARuntimeUnavailable(KJVARuntimeError):
    status_code = 503


@dataclass
class CognitiveResult:
    text: str
    trace_id: str
    backend_name: str
    retrieved: bool
    metadata: Dict[str, Any] = field(default_factory=dict)


class ConstitutionRuntime:
    """Runtime interpretation of ``KJVA/constitution`` doctrine files."""

    def __init__(self) -> None:
        self.docs_dir = _KJVA_ROOT / "constitution"
        self.vacancy_matrix = VacancyMatrix()
        self.attestation = AttestationEngine()
        self.member_guard = MemberGuard(
            vacancy_matrix=self.vacancy_matrix,
            attestation_engine=self.attestation,
        )
        self._attested = False
        self._last_attestation: Dict[str, Any] = {}

    def preflight(self, trace_id: str, prompt: str, operation: str) -> DecisionOutcome:
        missing_docs = [
            str(self.docs_dir / filename)
            for filename in CONSTITUTION_DOCS.values()
            if not (self.docs_dir / filename).exists()
        ]
        if missing_docs:
            return DecisionOutcome.deny(
                trace_id=trace_id,
                authority="constitution",
                reason_code="CONSTITUTION_DOC_MISSING",
                detail=f"Constitution doctrine files missing: {missing_docs}",
                severity="CRITICAL",
            )

        if not self.member_guard.verify_registry_integrity():
            return DecisionOutcome.deny(
                trace_id=trace_id,
                authority="seat_protection_doctrine",
                reason_code="MEMBER_REGISTRY_TAMPERED",
                detail="Seat protection doctrine blocked runtime: registry integrity mismatch.",
                severity="CRITICAL",
            )

        if not self._attested:
            attestation = self._attest_runtime(trace_id)
            if not attestation.allowed:
                return attestation

        degraded = self.vacancy_matrix.is_degraded()
        if degraded:
            prompt_lower = prompt.lower()
            high_risk = operation in {"generate", "persist"} and any(
                phrase in prompt_lower
                for phrase in (
                    "delete",
                    "override",
                    "ignore covenant",
                    "disable",
                    "identity",
                    "registry",
                    "member",
                    "governance",
                )
            )
            if high_risk or not self.vacancy_matrix.get_regency_triad_active():
                return DecisionOutcome.deny(
                    trace_id=trace_id,
                    authority="degraded_mode_matrix",
                    reason_code="DEGRADED_MODE_BLOCK",
                    detail="Degraded mode matrix blocks high-risk or regency-unsafe action.",
                    severity="CRITICAL",
                    metadata={"seat_status": self.vacancy_matrix.get_all_statuses()},
                )
            return DecisionOutcome.warn(
                trace_id=trace_id,
                authority="degraded_mode_matrix",
                reason_code="DEGRADED_MODE_CONTINUE",
                detail="Request allowed with degraded-mode disclosure.",
                metadata={"seat_status": self.vacancy_matrix.get_all_statuses()},
            )

        return DecisionOutcome.allow(
            trace_id=trace_id,
            authority="constitution",
            reason_code="CONSTITUTION_PREFLIGHT_PASS",
            metadata={
                "docs": CONSTITUTION_DOCS,
                "attestation": self._last_attestation,
            },
        )

    def _attest_runtime(self, trace_id: str) -> DecisionOutcome:
        members = ("Sarah", "Esther", "Magen", "Abigail", "Ruth", "Ezri", "Ahki")
        results: Dict[str, str] = {}
        vacant = self.vacancy_matrix.get_vacant_seats()
        for member in members:
            if member not in MEMBER_REGISTRY:
                return DecisionOutcome.deny(
                    trace_id=trace_id,
                    authority="identity_attestation_doctrine",
                    reason_code="MEMBER_NOT_REGISTERED",
                    detail=f"{member} is absent from MEMBER_REGISTRY.",
                    severity="CRITICAL",
                )
            schema_hash = self.attestation.compute_schema_hash(member)
            lineage = hashlib.sha256(
                f"{AGENT_ID}:{member}:{schema_hash}".encode("utf-8")
            ).hexdigest()
            result = self.attestation.attest(member, schema_hash, lineage, vacant)
            results[member] = result.status.name
            if result.status is not AttestationStatus.VERIFIED:
                return DecisionOutcome.deny(
                    trace_id=trace_id,
                    authority="identity_attestation_doctrine",
                    reason_code="IDENTITY_ATTESTATION_FAILED",
                    detail=f"{member} attestation failed: {result.reason}",
                    severity="CRITICAL",
                    metadata={"checks_failed": result.checks_failed},
                )
        self._attested = True
        self._last_attestation = results
        return DecisionOutcome.allow(
            trace_id=trace_id,
            authority="identity_attestation_doctrine",
            reason_code="IDENTITY_ATTESTED",
            metadata=results,
        )


class KjvaBibleAgent(TokenlessAgentWithHeptagon):
    """Tokenless agent whose core generation is XMIND, not canned text."""

    def __init__(self, config: AgentConfig, heptagon: HeptagonLayer, backend: Any) -> None:
        super().__init__(config, heptagon)
        self._backend = backend
        self._generation_options: Dict[str, Any] = {}

    def generate(
        self,
        session_id: str,
        prompt: str,
        max_new_tokens: int,
        temperature: float,
        top_p: float,
    ) -> str:
        self._generation_options = {
            "max_new_tokens": max_new_tokens,
            "temperature": temperature,
            "top_p": top_p,
        }
        try:
            return self.chat(session_id, prompt)
        finally:
            self._generation_options = {}

    def _process(self, message: str, history: list[dict[str, str]]) -> str:
        del history
        options = self._generation_options or {}
        return self._backend.complete(
            message,
            max_new_tokens=int(options.get("max_new_tokens", 150)),
            temperature=float(options.get("temperature", 0.8)),
            top_p=float(options.get("top_p", 0.9)),
        )


class KJVAConstitutionalRuntime:
    def __init__(self) -> None:
        self.constitution = ConstitutionRuntime()
        self.engine = get_engine()
        self.covenant = CovenantEnforcer()
        self.gate_chain = create_default_gate_chain()
        self.governance = GovernanceInterceptors(self.gate_chain)
        self.soul_journal_dir = Path(
            os.environ.get("KJVA_SOUL_JOURNAL_DIR", str(_REPO_ROOT / "data" / "soul_journal"))
        )
        self.soul: Optional[SoulManager] = None
        self.heptagon = HeptagonLayer.build(agent_id=AGENT_ID)
        self.agent = KjvaBibleAgent(
            AgentConfig(agent_id=AGENT_ID, temperature=0.8),
            self.heptagon,
            self.engine,
        )
        self.ready = False
        self.bootstrap_error = ""

    async def bootstrap(self) -> None:
        try:
            self.soul_journal_dir.mkdir(parents=True, exist_ok=True)
            os.chmod(self.soul_journal_dir, 0o700)
            self.soul = SoulManager(journal_dir=str(self.soul_journal_dir))
            if os.environ.get("TOKENLESS_SOUL_ALLOW_PLAINTEXT", "0").strip() == "1":
                await self.soul.put(
                    AGENT_ID,
                    "meta",
                    f"security/plaintext-warning-{int(time.time())}",
                    {
                        "event": "TOKENLESS_SOUL_ALLOW_PLAINTEXT",
                        "severity": "WARN",
                        "detail": (
                            "Dev-only plaintext escape hatch is active. "
                            "This runtime mode is not permitted for production."
                        ),
                        "authority": "soul_manager",
                    },
                )
            self.ready = True
            self.bootstrap_error = ""
        except Exception as exc:  # noqa: BLE001
            self.ready = False
            self.bootstrap_error = str(exc)

    def health(self) -> Dict[str, Any]:
        engine_status = self.engine.status() if hasattr(self.engine, "status") else {}
        return {
            "cognitive_ready": self.ready,
            "constitution_ready": self.constitution.preflight(
                trace_id="health",
                prompt="health",
                operation="health",
            ).allowed,
            "bootstrap_error": self.bootstrap_error,
            "gate_chain_members": 7,
            "soul_journal_path": str(self.soul_journal_dir),
            "xmind": engine_status,
            "mlx_serving_enabled": False,
            "contract_roots": [
                "KJVA/constitution",
                "KJVA/governance",
                "KJVA/heptagon",
                "KJVA/ai/xmind",
                "KJVA/soul_manager",
            ],
        }

    async def complete(
        self,
        prompt: str,
        max_new_tokens: int,
        temperature: float,
        top_p: float,
    ) -> CognitiveResult:
        trace_id = self._trace_id(prompt)
        outcomes: list[DecisionOutcome] = []
        try:
            self._require_ready(trace_id)
            outcomes.append(self._constitutional_preflight(trace_id, prompt, "generate"))
            route = self._before_route(trace_id, prompt)
            outcomes.append(route)
            covenant = self._covenant_enforce(trace_id, prompt)
            outcomes.append(covenant)
            gate = self._before_execute(trace_id, prompt, retrieved=False)
            outcomes.append(gate)
            self._raise_if_heptagon_stopped(trace_id, "HEPTAGON_PRE_HARD_STOP")

            if not self.engine.is_ready():
                raise KJVARuntimeUnavailable(DecisionOutcome.deny(
                    trace_id=trace_id,
                    authority="ai/xmind",
                    reason_code="XMIND_BACKEND_NOT_READY",
                    detail=(
                        "XMIND byte backend is not ready. "
                        f"{getattr(self.engine, 'last_error', '')}"
                    ),
                    severity="ERROR",
                ))

            response = self.agent.generate(
                session_id=trace_id,
                prompt=prompt,
                max_new_tokens=max_new_tokens,
                temperature=temperature,
                top_p=top_p,
            )
            verification_meta = self._verify_heptagon_response(trace_id, prompt, response)
            record = await self._persist_record(
                trace_id=trace_id,
                prompt=prompt,
                response=response,
                retrieved=False,
                status="completed",
                outcomes=outcomes,
                metadata=verification_meta,
            )
            self.governance.citadel_after_event(
                "completion.completed",
                {"trace_id": trace_id, "soul_key": record["soul_key"]},
                source=AGENT_ID,
            )
            return CognitiveResult(
                text=response,
                trace_id=trace_id,
                backend_name=getattr(self.engine, "backend_name", "xmind"),
                retrieved=False,
                metadata=self._metadata(outcomes, record, verification_meta),
            )
        except KJVARuntimeError as exc:
            await self._record_failure(trace_id, prompt, exc.outcome, outcomes)
            raise
        except XmindPolicyHalt as exc:
            outcome = DecisionOutcome.deny(
                trace_id=trace_id,
                authority="ai/xmind",
                reason_code="XMIND_POLICY_HALT",
                detail=str(exc),
                severity="CRITICAL",
            )
            await self._record_failure(trace_id, prompt, outcome, outcomes)
            raise KJVARuntimeDenied(outcome) from exc
        except XmindBackendError as exc:
            outcome = DecisionOutcome.deny(
                trace_id=trace_id,
                authority="ai/xmind",
                reason_code="XMIND_BACKEND_ERROR",
                detail=str(exc),
                severity="ERROR",
            )
            await self._record_failure(trace_id, prompt, outcome, outcomes)
            raise KJVARuntimeUnavailable(outcome) from exc
        except Exception as exc:  # noqa: BLE001
            outcome = DecisionOutcome.deny(
                trace_id=trace_id,
                authority="runtime",
                reason_code="RUNTIME_FAILURE",
                detail=str(exc),
                severity="ERROR",
            )
            await self._record_failure(trace_id, prompt, outcome, outcomes)
            raise KJVARuntimeUnavailable(outcome) from exc

    async def persist_retrieval(
        self,
        prompt: str,
        response: str,
        metadata: Dict[str, Any],
    ) -> CognitiveResult:
        trace_id = self._trace_id(prompt)
        outcomes: list[DecisionOutcome] = []
        try:
            self._require_ready(trace_id)
            outcomes.append(self._constitutional_preflight(trace_id, prompt, "retrieve"))
            outcomes.append(self._before_route(trace_id, prompt))
            outcomes.append(self._covenant_enforce(trace_id, prompt))
            outcomes.append(self._before_execute(trace_id, prompt, retrieved=True))
            self._raise_if_heptagon_stopped(trace_id, "HEPTAGON_PRE_HARD_STOP")
            record = await self._persist_record(
                trace_id=trace_id,
                prompt=prompt,
                response=response,
                retrieved=True,
                status="completed",
                outcomes=outcomes,
                metadata=metadata,
            )
            self.governance.citadel_after_event(
                "completion.retrieved",
                {"trace_id": trace_id, "soul_key": record["soul_key"]},
                source=AGENT_ID,
            )
            return CognitiveResult(
                text=response,
                trace_id=trace_id,
                backend_name="kjva-retrieval",
                retrieved=True,
                metadata=self._metadata(outcomes, record, metadata),
            )
        except KJVARuntimeError as exc:
            await self._record_failure(trace_id, prompt, exc.outcome, outcomes)
            raise
        except Exception as exc:  # noqa: BLE001
            outcome = DecisionOutcome.deny(
                trace_id=trace_id,
                authority="runtime",
                reason_code="RUNTIME_FAILURE",
                detail=str(exc),
                severity="ERROR",
            )
            await self._record_failure(trace_id, prompt, outcome, outcomes)
            raise KJVARuntimeUnavailable(outcome) from exc

    def _trace_id(self, prompt: str) -> str:
        digest = hashlib.sha256(f"{time.time_ns()}:{prompt}".encode("utf-8")).hexdigest()[:16]
        return f"kjva-{digest}"

    def _require_ready(self, trace_id: str) -> None:
        if not self.ready or self.soul is None:
            raise KJVARuntimeUnavailable(DecisionOutcome.deny(
                trace_id=trace_id,
                authority="runtime",
                reason_code="RUNTIME_NOT_BOOTSTRAPPED",
                detail=self.bootstrap_error or "KJVA runtime bootstrap has not completed.",
                severity="CRITICAL",
            ))

    def _constitutional_preflight(self, trace_id: str, prompt: str, operation: str) -> DecisionOutcome:
        outcome = self.constitution.preflight(trace_id, prompt, operation)
        if not outcome.allowed:
            raise KJVARuntimeDenied(outcome)
        return outcome

    def _before_route(self, trace_id: str, prompt: str) -> DecisionOutcome:
        result = self.governance.citadel_before_route(
            destination="TOKENLESS_INTERFACE",
            payload={"trace_id": trace_id, "prompt_hash": self._hash(prompt)},
            sender=AGENT_ID,
        )
        outcome = self._from_intercept(result, trace_id, "governance.before_route")
        if not outcome.allowed:
            raise KJVARuntimeDenied(outcome)
        return outcome

    def _covenant_enforce(self, trace_id: str, prompt: str) -> DecisionOutcome:
        result = self.covenant.enforce(
            prompt,
            context={"trace_id": trace_id, "endpoint": "/api/complete"},
        )
        if result.action is EnforcementAction.BLOCK:
            raise KJVACovenantDenied(DecisionOutcome.deny(
                trace_id=trace_id,
                authority="covenant",
                reason_code="COVENANT_BLOCK",
                detail=result.summary(),
                severity="CRITICAL",
                metadata={"violations": [v.covenant_id for v in result.violations]},
            ))
        if result.action is EnforcementAction.WARN:
            return DecisionOutcome.warn(
                trace_id=trace_id,
                authority="covenant",
                reason_code="COVENANT_WARN",
                detail=result.summary(),
            )
        return DecisionOutcome.allow(trace_id, "covenant", "COVENANT_ALLOW")

    def _before_execute(self, trace_id: str, prompt: str, retrieved: bool) -> DecisionOutcome:
        context = {
            "trace_id": trace_id,
            "endpoint": "/api/complete",
            "domains": ["scripture_completion", "kjva_bible"],
            "constraints": [
                "preserve covenant",
                "never delete memory",
                "use XMIND for generation",
                "retrieval first",
            ],
            "evidence": [
                "KJVA/constitution/degraded_mode_matrix.md",
                "KJVA/governance",
                "KJVA/heptagon",
                "KJVA/ai/xmind",
                "KJVA/soul_manager",
            ],
            "resources": {
                "retrieved": retrieved,
                "backend": "kjva-retrieval" if retrieved else "xmind-byte-host",
            },
            "risk_score": 0.08 if retrieved else 0.18,
            "value_score": 0.93,
            "provenance_hash": self._hash(f"{trace_id}:{prompt}"),
        }
        result = self.governance.citadel_before_execute(
            intent=prompt,
            subject="scripture_completion preserve covenant KJVA Bible",
            context=context,
            created_by=CREATED_BY,
        )
        outcome = self._from_intercept(result, trace_id, "governance.before_execute")
        if not outcome.allowed:
            raise KJVARuntimeDenied(outcome)
        return outcome

    def _raise_if_heptagon_stopped(self, trace_id: str, reason_code: str) -> None:
        enforcer = getattr(self.heptagon, "enforcer", None)
        if enforcer is not None and getattr(enforcer, "is_hard_stopped", lambda: False)():
            raise KJVARuntimeDenied(DecisionOutcome.deny(
                trace_id=trace_id,
                authority="heptagon",
                reason_code=reason_code,
                detail="Heptagon L7 hard stop is active.",
                severity="CRITICAL",
            ))

    def _verify_heptagon_response(self, trace_id: str, prompt: str, response: str) -> Dict[str, Any]:
        verification_meta: Dict[str, Any] = {}
        verifier = getattr(self.heptagon, "verifier", None)
        if verifier is not None:
            result = verifier.verify(prompt, response)
            verification_meta = {
                "verification_passed": bool(getattr(result, "passed", False)),
                "verification_score": float(getattr(result, "score", 0.0)),
                "verification_flags": list(getattr(result, "flags", [])),
            }
            if not getattr(result, "passed", False):
                raise KJVARuntimeDenied(DecisionOutcome.deny(
                    trace_id=trace_id,
                    authority="heptagon",
                    reason_code="HEPTAGON_VERIFICATION_DENY",
                    detail=f"Heptagon L5 verification failed: {verification_meta}",
                    severity="ERROR",
                    metadata=verification_meta,
                ))
        self._raise_if_heptagon_stopped(trace_id, "HEPTAGON_POST_HARD_STOP")
        return verification_meta

    async def _persist_record(
        self,
        trace_id: str,
        prompt: str,
        response: str,
        retrieved: bool,
        status: str,
        outcomes: list[DecisionOutcome],
        metadata: Dict[str, Any],
    ) -> Dict[str, Any]:
        if self.soul is None:
            raise KJVARuntimeUnavailable(DecisionOutcome.deny(
                trace_id=trace_id,
                authority="soul_manager",
                reason_code="SOUL_MANAGER_UNAVAILABLE",
                detail="SoulManager is not initialized.",
                severity="CRITICAL",
            ))
        payload = {
            "trace_id": trace_id,
            "status": status,
            "prompt": prompt,
            "response": response,
            "retrieved": retrieved,
            "backend": "kjva-retrieval" if retrieved else getattr(self.engine, "backend_name", "xmind"),
            "outcomes": [outcome.to_dict() for outcome in outcomes],
            "metadata": metadata,
            "created_at": time.time(),
        }
        content_hash = self._hash(json.dumps(payload, sort_keys=True, default=str))
        storage = StorageEnvelope(
            classification=Classification.INTERNAL,
            retention_class=RetentionClass.PERMANENT,
            origin_authority=AGENT_ID,
            policy_stamp=trace_id,
            alignment_stamp=trace_id,
            trust_stamp=trace_id,
            knowledge_stamp=trace_id,
            provenance_root=trace_id,
            content_hash=content_hash,
        )
        persist_result = self.governance.citadel_before_persist(storage)
        persist_outcome = self._from_intercept(
            persist_result,
            trace_id,
            "governance.before_persist",
        )
        if not persist_outcome.allowed:
            raise KJVARuntimeDenied(persist_outcome)
        payload["outcomes"].append(persist_outcome.to_dict())
        payload["storage_envelope"] = storage.to_dict()
        sub_path = f"{int(time.time() * 1000)}-{trace_id}-{uuid.uuid4().hex[:8]}"
        try:
            await self.soul.put(AGENT_ID, "episodic", sub_path, payload)
        except Exception as exc:  # noqa: BLE001
            raise KJVARuntimeUnavailable(DecisionOutcome.deny(
                trace_id=trace_id,
                authority="soul_manager",
                reason_code="SOUL_PERSIST_FAILED",
                detail=str(exc),
                severity="CRITICAL",
            )) from exc
        self._secure_journal_files()
        return {
            "soul_key": sub_path,
            "storage_envelope": storage.to_dict(),
            "persist_outcome": persist_outcome.to_dict(),
        }

    async def _record_failure(
        self,
        trace_id: str,
        prompt: str,
        outcome: DecisionOutcome,
        prior_outcomes: list[DecisionOutcome],
    ) -> None:
        self.governance.citadel_after_failure(
            outcome.reason_code,
            outcome.to_dict(),
            source=outcome.authority,
        )
        if self.soul is None:
            return
        try:
            await self._persist_record(
                trace_id=trace_id,
                prompt=prompt,
                response="",
                retrieved=False,
                status="denied",
                outcomes=prior_outcomes + [outcome],
                metadata={"failure": outcome.to_dict()},
            )
        except Exception:  # noqa: BLE001
            self.governance.citadel_after_failure(
                "FAILURE_PERSIST_FAILED",
                {"trace_id": trace_id, "original_failure": outcome.to_dict()},
                source="soul_manager",
            )

    def _metadata(
        self,
        outcomes: list[DecisionOutcome],
        record: Dict[str, Any],
        extra: Dict[str, Any],
    ) -> Dict[str, Any]:
        event_log = self.governance.get_event_log()
        return {
            "trace_id": outcomes[0].trace_id if outcomes else "",
            "backend": getattr(self.engine, "backend_name", "xmind"),
            "outcomes": [outcome.to_dict() for outcome in outcomes],
            "gates_passed": 7 if any(o.reason_code == "ALLOW" and o.authority == "all_passed" for o in outcomes) else None,
            "soul_key": record.get("soul_key"),
            "storage_envelope": record.get("storage_envelope"),
            "persist_outcome": record.get("persist_outcome"),
            "governance_event_count": len(event_log),
            **extra,
        }

    def _from_intercept(self, result: Any, trace_id: str, authority: str) -> DecisionOutcome:
        if result.allowed:
            return DecisionOutcome.allow(
                trace_id=trace_id,
                authority=result.authority or authority,
                reason_code="ALLOW",
                detail=result.reason,
                metadata={"envelope_id": result.envelope_id},
            )
        return DecisionOutcome.deny(
            trace_id=trace_id,
            authority=result.authority or authority,
            reason_code="INTERCEPT_DENY",
            detail=result.reason,
            severity="ERROR",
            metadata={"envelope_id": result.envelope_id},
        )

    def _secure_journal_files(self) -> None:
        for path in self.soul_journal_dir.glob("*.jsonl"):
            try:
                os.chmod(path, 0o600)
            except OSError:
                pass

    def _hash(self, value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()


_runtime: Optional[KJVAConstitutionalRuntime] = None


def get_runtime() -> KJVAConstitutionalRuntime:
    global _runtime
    if _runtime is None:
        _runtime = KJVAConstitutionalRuntime()
    return _runtime
