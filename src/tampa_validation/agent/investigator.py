"""Structured contracts and coordinator for evidence-only investigations.

Nothing in this module can write a frozen sample, a human review, or a release
validation result.  The only downstream artifact is a candidate-only handoff
that an independently configured deterministic evaluator may consume.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
import json
from pathlib import Path
import re
from typing import Any, Mapping

from .planner import InvestigationPlan, InvestigationPlanner
from .provenance import (
    AuditTrail,
    DeterministicHandoff,
    ModelMetadata,
    PromptProvenance,
    canonical_json,
    sha256_payload,
)
from .safety import ALLOWED_INVESTIGATION_STATUSES, assert_safe_agent_output
from .sources import SourceTier
from .tools import InvestigationTools


_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_CLAIM = re.compile(r"^[a-z][a-z0-9_]{0,127}$")


def _detached_json(value: Any) -> Any:
    return json.loads(canonical_json(value))


def _required_identifier(name: str, value: str) -> None:
    if not _ID.fullmatch(value):
        raise ValueError(f"{name} must be a simple non-empty identifier")


class InvestigationStatus(str, Enum):
    EVIDENCE_FOUND = "evidence_found"
    CONFLICTING_EVIDENCE_FOUND = "conflicting_evidence_found"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    AMBIGUOUS_IDENTITY = "ambiguous_identity"
    SOURCE_UNAVAILABLE = "source_unavailable"
    RETRIEVAL_ERROR = "retrieval_error"
    NO_ADDITIONAL_EVIDENCE_FOUND = "no_additional_evidence_found"
    INVESTIGATION_BUDGET_EXHAUSTED = "investigation_budget_exhausted"


assert {status.value for status in InvestigationStatus} == set(ALLOWED_INVESTIGATION_STATUSES)


class IdentityCategory(str, Enum):
    EXACT_IDENTIFIER = "exact_identifier"
    STRONG_MULTI_FIELD = "strong_multi_field"
    AMBIGUOUS = "ambiguous"
    CONFLICTING = "conflicting"
    REJECTED = "rejected"


@dataclass(frozen=True)
class InvestigationRequest:
    study: str
    sample_id: str
    activity_id: str
    unresolved_claims: tuple[str, ...]
    record_number: str = ""
    record_type: str = ""
    address: str = ""
    parcel_id: str = ""
    project_name: str = ""
    known_dates: Mapping[str, str] = field(default_factory=dict)
    known_evidence: tuple[Mapping[str, Any], ...] = ()

    def __post_init__(self) -> None:
        _required_identifier("study", self.study)
        _required_identifier("sample_id", self.sample_id)
        _required_identifier("activity_id", self.activity_id)
        if not self.unresolved_claims:
            raise ValueError("at least one unresolved claim is required")
        if any(not _CLAIM.fullmatch(claim) for claim in self.unresolved_claims):
            raise ValueError("unresolved claims must use stable lower_snake_case names")
        if len(set(self.unresolved_claims)) != len(self.unresolved_claims):
            raise ValueError("unresolved claims must not be duplicated")
        canonical_json(self.known_dates)
        canonical_json(self.known_evidence)

    @classmethod
    def from_mapping(cls, values: Mapping[str, Any]) -> "InvestigationRequest":
        allowed = {field.name for field in cls.__dataclass_fields__.values()}
        extra = set(values).difference(allowed)
        if extra:
            raise ValueError("unknown investigation request fields: " + ", ".join(sorted(extra)))
        converted = dict(values)
        converted["unresolved_claims"] = tuple(converted.get("unresolved_claims", ()))
        converted["known_evidence"] = tuple(
            _detached_json(item) for item in converted.get("known_evidence", ())
        )
        converted["known_dates"] = _detached_json(converted.get("known_dates", {}))
        return cls(**converted)

    def as_dict(self) -> dict[str, Any]:
        return _detached_json(asdict(self))


@dataclass(frozen=True)
class IdentityAssessment:
    category: IdentityCategory
    identity_match_method: str
    exact_identifiers: Mapping[str, str] = field(default_factory=dict)
    supporting_fields: tuple[str, ...] = ()
    conflicting_fields: tuple[str, ...] = ()
    candidate_count: int = 0
    accepted_for_rule_evaluation: bool = False

    def __post_init__(self) -> None:
        if not self.identity_match_method.strip():
            raise ValueError("identity_match_method is required")
        if (
            isinstance(self.candidate_count, bool)
            or not isinstance(self.candidate_count, int)
            or self.candidate_count < 0
        ):
            raise ValueError("candidate_count must be a non-negative integer")
        canonical_json(self.exact_identifiers)
        if self.accepted_for_rule_evaluation:
            if self.category is not IdentityCategory.EXACT_IDENTIFIER:
                raise ValueError("only an exact identifier may enter the current rule registry")
            if self.candidate_count != 1 or self.conflicting_fields:
                raise ValueError("accepted identity requires one candidate and no conflicting fields")
            if not self.exact_identifiers:
                raise ValueError("accepted identity requires a documented exact identifier")
            if any(not str(key).strip() or not str(value).strip() for key, value in self.exact_identifiers.items()):
                raise ValueError("exact identifiers require non-empty field names and values")

    @property
    def confidence(self) -> str:
        """An interpretable category, never an invented numeric probability."""
        return self.category.value

    def as_dict(self) -> dict[str, Any]:
        values = _detached_json(asdict(self))
        values["confidence"] = self.confidence
        return values


@dataclass(frozen=True)
class CandidateEvidence:
    evidence_id: str
    source_tier: SourceTier
    evidence_type: str
    extracted_fields: Mapping[str, Any]
    identity: IdentityAssessment
    concise_interpretation: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.source_tier, SourceTier):
            raise ValueError("source_tier must be a documented SourceTier")
        if not re.fullmatch(r"[0-9a-f]{64}", self.evidence_id):
            raise ValueError("candidate evidence_id must reference an archived SHA-256 identifier")
        if not self.evidence_type.strip():
            raise ValueError("candidate evidence_type is required")
        canonical_json(self.extracted_fields)
        if len(self.concise_interpretation) > 600:
            raise ValueError("candidate interpretation must remain concise")

    def as_dict(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "source_tier": self.source_tier.value,
            "evidence_type": self.evidence_type,
            "extracted_fields": _detached_json(self.extracted_fields),
            "identity": self.identity.as_dict(),
            "concise_interpretation": self.concise_interpretation,
        }


_NEXT_ACTIONS = {
    "deterministic_re_evaluation",
    "human_review",
    "retry_authoritative_source",
    "no_further_action",
}


@dataclass(frozen=True)
class InvestigationResult:
    investigation_id: str
    sample_id: str
    claim: str
    status: InvestigationStatus
    candidate_evidence: tuple[CandidateEvidence, ...] = ()
    conflicts: tuple[str, ...] = ()
    missing_information: tuple[str, ...] = ()
    recommended_next_action: str = "human_review"
    requires_human_review: bool = True
    concise_summary: str = ""

    def __post_init__(self) -> None:
        _required_identifier("investigation_id", self.investigation_id)
        _required_identifier("sample_id", self.sample_id)
        if not isinstance(self.status, InvestigationStatus):
            raise ValueError("status must be a permitted InvestigationStatus")
        if not _CLAIM.fullmatch(self.claim):
            raise ValueError("claim must be a stable lower_snake_case name")
        if self.recommended_next_action not in _NEXT_ACTIONS:
            raise ValueError("invalid recommended_next_action")
        if len(self.concise_summary) > 1000:
            raise ValueError("result summary must remain concise")
        if self.status is InvestigationStatus.EVIDENCE_FOUND and not self.candidate_evidence:
            raise ValueError("evidence_found requires archived candidate evidence")
        if self.status is InvestigationStatus.CONFLICTING_EVIDENCE_FOUND and not self.conflicts:
            raise ValueError("conflicting_evidence_found requires documented conflicts")
        if self.status in {
            InvestigationStatus.AMBIGUOUS_IDENTITY,
            InvestigationStatus.CONFLICTING_EVIDENCE_FOUND,
            InvestigationStatus.INSUFFICIENT_EVIDENCE,
            InvestigationStatus.INVESTIGATION_BUDGET_EXHAUSTED,
        } and not self.requires_human_review:
            raise ValueError(f"{self.status.value} must require human review")
        if not self.requires_human_review:
            if self.status is not InvestigationStatus.EVIDENCE_FOUND:
                raise ValueError("only an evidence candidate eligible for rules may avoid immediate review")
            if self.recommended_next_action != "deterministic_re_evaluation":
                raise ValueError("non-human next action must be deterministic re-evaluation")
            if any(not candidate.identity.accepted_for_rule_evaluation for candidate in self.candidate_evidence):
                raise ValueError("all candidates must pass deterministic identity eligibility")
            if any(
                candidate.source_tier
                not in {SourceTier.ARCHIVED_PRIMARY, SourceTier.LIVE_PRIMARY}
                for candidate in self.candidate_evidence
            ):
                raise ValueError("only primary evidence can proceed without immediate human review")
        assert_safe_agent_output(self.as_dict())

    def as_dict(self) -> dict[str, Any]:
        return {
            "investigation_id": self.investigation_id,
            "sample_id": self.sample_id,
            "claim": self.claim,
            "status": self.status.value,
            "candidate_evidence": [candidate.as_dict() for candidate in self.candidate_evidence],
            "conflicts": list(self.conflicts),
            "missing_information": list(self.missing_information),
            "recommended_next_action": self.recommended_next_action,
            "requires_human_review": self.requires_human_review,
            "concise_summary": self.concise_summary,
        }


@dataclass(frozen=True)
class InvestigationSession:
    investigation_id: str
    request: InvestigationRequest
    plans: tuple[InvestigationPlan, ...]
    tools: InvestigationTools
    audit_trail: AuditTrail


class EvidenceInvestigator:
    """Coordinate structured requests, plans, tools, and safe result finalization."""

    def __init__(self, tools: InvestigationTools, planner: InvestigationPlanner | None = None) -> None:
        self.tools = tools
        self.planner = planner or InvestigationPlanner()

    def start(
        self,
        request: InvestigationRequest,
        *,
        investigation_id: str,
        model_metadata: ModelMetadata | None = None,
        prompt_provenance: Mapping[str, PromptProvenance] | None = None,
    ) -> InvestigationSession:
        _required_identifier("investigation_id", investigation_id)
        plans = self.planner.create_plans(request)
        audit = self.tools.audit_trail or AuditTrail()
        if self.tools.audit_trail is None:
            self.tools.audit_trail = audit
        audit.append(
            "investigation_started",
            {
                "investigation_id": investigation_id,
                "study": request.study,
                "sample_id": request.sample_id,
                "activity_id": request.activity_id,
                "unresolved_claims": request.unresolved_claims,
                "request_hash": sha256_payload(request.as_dict()),
                "plans": [plan.as_dict() for plan in plans],
                "model_metadata": asdict(model_metadata or ModelMetadata()),
                "prompt_provenance": {
                    name: asdict(provenance)
                    for name, provenance in (prompt_provenance or {}).items()
                },
            },
        )
        return InvestigationSession(investigation_id, request, plans, self.tools, audit)

    def finalize(self, session: InvestigationSession, result: InvestigationResult) -> InvestigationResult:
        if result.investigation_id != session.investigation_id:
            raise ValueError("result investigation_id does not match its session")
        if result.sample_id != session.request.sample_id:
            raise ValueError("result sample_id does not match its request")
        if result.claim not in session.request.unresolved_claims:
            raise ValueError("agent may only report a claim listed as unresolved")
        assert_safe_agent_output(result.as_dict())
        session.audit_trail.append("investigation_result", result.as_dict())
        if session.tools.budget_tracker is not None:
            session.audit_trail.append(
                "investigation_usage", session.tools.budget_tracker.as_dict()
            )
        return result


def _assert_registry_boundaries(registry: Mapping[str, Any]) -> None:
    change_policy = registry.get("change_policy", {})
    if not isinstance(change_policy, Mapping):
        raise ValueError("rule registry change_policy must be an object")
    if change_policy.get("agent_may_activate_rules") is not False:
        raise ValueError("rule registry must explicitly prohibit agent rule activation")
    if "agent_may_activate_rules" in registry and registry["agent_may_activate_rules"] is not False:
        raise ValueError("rule registry must explicitly prohibit agent rule activation")
    if registry.get("may_modify_dataset_validation") is not False:
        raise ValueError("rule registry must prohibit dataset-validation writes")
    if registry.get("may_modify_human_review") is not False:
        raise ValueError("rule registry must prohibit human-review writes")
    if registry.get("release_activation_requires_human_approval") is not True:
        raise ValueError("rule registry must require human approval for release activation")


def load_rule_registry(path: Path | str) -> Mapping[str, Any]:
    registry = json.loads(Path(path).read_text(encoding="utf-8"))
    _assert_registry_boundaries(registry)
    return registry


def create_deterministic_handoff(
    result: InvestigationResult,
    *,
    rule_id: str,
    registry: Mapping[str, Any],
) -> DeterministicHandoff:
    """Create a pending envelope for a documented experimental rule.

    This function intentionally has no operation that applies the rule or writes
    its result.  Release-disabled and human-approval-required flags remain the
    responsibility of the separate deterministic evaluation pipeline.
    """
    _assert_registry_boundaries(registry)
    rules = {rule.get("rule_id"): rule for rule in registry.get("rules", ())}
    if rule_id not in rules:
        raise ValueError("handoff rule is absent from the documented registry")
    rule = rules[rule_id]
    if rule.get("claim") != result.claim:
        raise ValueError("handoff rule does not govern the investigated claim")
    if result.status is not InvestigationStatus.EVIDENCE_FOUND:
        raise ValueError("only evidence_found results can enter deterministic re-evaluation")
    eligible = tuple(
        candidate
        for candidate in result.candidate_evidence
        if candidate.identity.accepted_for_rule_evaluation
        and candidate.source_tier in {SourceTier.ARCHIVED_PRIMARY, SourceTier.LIVE_PRIMARY}
    )
    if len(eligible) != len(result.candidate_evidence) or not eligible:
        raise ValueError("all handed-off evidence must have exact identity and primary provenance")
    if rule.get("release_write_enabled") is not False:
        raise ValueError("agent benchmark handoff requires release_write_enabled=false")
    return DeterministicHandoff(
        investigation_id=result.investigation_id,
        sample_id=result.sample_id,
        claim=result.claim,
        evidence_ids=tuple(candidate.evidence_id for candidate in eligible),
        discovered_by="agent",
        evaluated_by="deterministic_rule",
        rule_id=rule_id,
    )


__all__ = [
    "CandidateEvidence",
    "EvidenceInvestigator",
    "IdentityAssessment",
    "IdentityCategory",
    "InvestigationRequest",
    "InvestigationResult",
    "InvestigationSession",
    "InvestigationStatus",
    "create_deterministic_handoff",
    "load_rule_registry",
]
