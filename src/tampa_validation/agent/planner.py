"""Concise plans and hard stopping controls for evidence investigations."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from enum import Enum
import time
from typing import Any, Callable, Mapping, Protocol

from .provenance import sha256_payload
from .safety import BudgetExceeded, BudgetUsage, InvestigationBudget, enforce_budget


class RequestLike(Protocol):
    unresolved_claims: tuple[str, ...]


@dataclass(frozen=True)
class InvestigationPlan:
    unresolved_claim: str
    strategy: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.unresolved_claim.strip():
            raise ValueError("a plan requires one unresolved claim")
        if not 1 <= len(self.strategy) <= 6:
            raise ValueError("an investigation plan must contain one to six concise steps")
        if any(not step.strip() or len(step) > 160 for step in self.strategy):
            raise ValueError("plan steps must be non-empty and concise")

    def as_dict(self) -> dict[str, Any]:
        return {
            "unresolved_claim": self.unresolved_claim,
            "strategy": list(self.strategy),
        }


_CLAIM_STRATEGIES: Mapping[str, tuple[str, ...]] = {
    "final_inspection_passed": (
        "search archived evidence for an exact administrative identifier",
        "retrieve inspection history for the matched administrative record",
        "locate an explicit final-building inspection type and result",
        "compare identifiers and conflicting fields",
        "archive candidate evidence for deterministic re-evaluation",
    ),
    "certificate_of_occupancy_issued": (
        "search archived evidence for an exact administrative identifier",
        "retrieve certificates or related official records",
        "distinguish permanent from temporary occupancy evidence",
        "compare identifiers and conflicting fields",
        "archive candidate evidence for deterministic re-evaluation",
    ),
}
_DEFAULT_STRATEGY = (
    "search archived primary evidence using exact identifiers",
    "search the relevant live primary source if archived evidence is insufficient",
    "compare administrative identifiers and conflicting fields",
    "archive relevant candidate evidence",
    "submit evidence for deterministic re-evaluation or human review",
)


class InvestigationPlanner:
    """Build a stable, externally useful plan without requesting reasoning traces."""

    def create_plans(self, request: RequestLike) -> tuple[InvestigationPlan, ...]:
        claims = tuple(dict.fromkeys(request.unresolved_claims))
        if not claims:
            raise ValueError("at least one unresolved claim is required")
        return tuple(
            InvestigationPlan(claim, _CLAIM_STRATEGIES.get(claim, _DEFAULT_STRATEGY))
            for claim in claims
        )


class StopReason(str, Enum):
    EVIDENCE_SUFFICIENT = "authoritative_evidence_sufficient"
    BUDGET_EXHAUSTED = "investigation_budget_exhausted"
    NO_MORE_CANDIDATES = "no_additional_evidence_found"
    SOURCE_UNAVAILABLE = "source_unavailable"
    MANUAL_REVIEW_REQUIRED = "human_review_required"


_SOURCE_QUERY_TOOLS = frozenset(
    {
        "search_accela",
        "search_city_gis",
        "search_archived_evidence",
        "search_inspections",
        "search_official_web",
    }
)


class BudgetTracker:
    """Account for work and reject the next action before it exceeds a limit."""

    def __init__(
        self,
        budget: InvestigationBudget,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.budget = budget
        self._clock = clock
        self._started = clock()
        self._usage = BudgetUsage()
        self._query_counts: dict[str, int] = {}

    @property
    def usage(self) -> BudgetUsage:
        elapsed = max(0.0, self._clock() - self._started)
        return replace(self._usage, duration_seconds=elapsed)

    def _project_tool_call(self, tool_name: str, parameters: Mapping[str, Any]) -> BudgetUsage:
        signature = sha256_payload({"tool": tool_name, "parameters": parameters})
        repeats = 1 if self._query_counts.get(signature, 0) >= 1 else 0
        return replace(
            self.usage,
            tool_calls=self._usage.tool_calls + 1,
            source_queries=self._usage.source_queries + int(tool_name in _SOURCE_QUERY_TOOLS),
            repeated_queries=self._usage.repeated_queries + repeats,
        )

    def authorize_tool_call(self, tool_name: str, parameters: Mapping[str, Any]) -> None:
        """Raise before dispatch if the proposed call would exceed a hard limit."""
        self.assert_within_duration()
        enforce_budget(self.budget, self._project_tool_call(tool_name, parameters))

    def record_tool_call(self, tool_name: str, parameters: Mapping[str, Any]) -> None:
        projected = self._project_tool_call(tool_name, parameters)
        signature = sha256_payload({"tool": tool_name, "parameters": parameters})
        self._query_counts[signature] = self._query_counts.get(signature, 0) + 1
        self._usage = replace(projected, duration_seconds=self._usage.duration_seconds)

    def record_model_usage(
        self,
        *,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cost_usd: float = 0.0,
    ) -> None:
        projected = replace(
            self.usage,
            input_tokens=self._usage.input_tokens + input_tokens,
            output_tokens=self._usage.output_tokens + output_tokens,
            cost_usd=self._usage.cost_usd + cost_usd,
        )
        enforce_budget(self.budget, projected)
        self._usage = replace(projected, duration_seconds=self._usage.duration_seconds)

    def assert_within_duration(self) -> None:
        usage = self.usage
        if usage.duration_seconds >= self.budget.max_duration_seconds:
            raise BudgetExceeded(
                "duration_seconds", usage.duration_seconds, self.budget.max_duration_seconds
            )

    def as_dict(self) -> dict[str, Any]:
        return asdict(self.usage)
