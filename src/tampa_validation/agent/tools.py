"""Narrow, structured tool boundary with deterministic recorded replay."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Callable, Mapping, Protocol, Sequence

from .planner import BudgetTracker
from .provenance import AuditTrail, canonical_json, sha256_payload
from .safety import redact_sensitive, wrap_untrusted_evidence


class ToolName(str, Enum):
    SEARCH_ACCELA = "search_accela"
    FETCH_ACCELA_RECORD = "fetch_accela_record"
    SEARCH_CITY_GIS = "search_city_gis"
    FETCH_CITY_RECORD = "fetch_city_record"
    SEARCH_ARCHIVED_EVIDENCE = "search_archived_evidence"
    SEARCH_INSPECTIONS = "search_inspections"
    SEARCH_OFFICIAL_WEB = "search_official_web"
    FETCH_OFFICIAL_DOCUMENT = "fetch_official_document"
    ARCHIVE_EVIDENCE = "archive_evidence"
    CALCULATE_HASH = "calculate_hash"
    SUBMIT_CANDIDATE_EVIDENCE = "submit_candidate_evidence"


class ToolStatus(str, Enum):
    OK = "ok"
    NOT_FOUND = "not_found"
    UNAVAILABLE = "unavailable"
    ERROR = "error"


@dataclass(frozen=True)
class ToolRequest:
    name: ToolName
    parameters: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Validate serializability and detach callers from any opaque objects.
        canonical_json(self.parameters)

    @property
    def request_hash(self) -> str:
        return sha256_payload({"name": self.name.value, "parameters": self.parameters})


@dataclass(frozen=True)
class ToolResult:
    status: ToolStatus
    data: Any = field(default_factory=dict)
    error_code: str = ""

    def __post_init__(self) -> None:
        canonical_json(self.data)
        if self.status is ToolStatus.ERROR and not self.error_code:
            raise ValueError("error tool results require a non-sensitive error_code")

    @property
    def result_hash(self) -> str:
        return sha256_payload(self.as_dict())

    def as_dict(self) -> dict[str, Any]:
        values = asdict(self)
        values["status"] = self.status.value
        return values

    def as_untrusted_prompt_data(self, *, source_label: str) -> str:
        return wrap_untrusted_evidence(self.as_dict(), source_label=source_label)


class ToolBackend(Protocol):
    def execute(self, request: ToolRequest) -> ToolResult: ...


@dataclass(frozen=True)
class RecordedExchange:
    request: ToolRequest
    result: ToolResult


class RecordedBackend:
    """Replay an exact cassette; it performs no network or filesystem access."""

    def __init__(self, exchanges: Sequence[RecordedExchange]) -> None:
        self._remaining = list(exchanges)
        self._consumed: list[RecordedExchange] = []

    @property
    def consumed(self) -> tuple[RecordedExchange, ...]:
        return tuple(self._consumed)

    @property
    def remaining(self) -> tuple[RecordedExchange, ...]:
        return tuple(self._remaining)

    def execute(self, request: ToolRequest) -> ToolResult:
        if not self._remaining:
            raise LookupError(f"no recorded response for {request.name.value}")
        exchange = self._remaining[0]
        if exchange.request.request_hash != request.request_hash:
            raise LookupError(
                f"recorded request mismatch: expected {exchange.request.name.value} "
                f"({exchange.request.request_hash}), got {request.name.value} "
                f"({request.request_hash})"
            )
        self._remaining.pop(0)
        self._consumed.append(exchange)
        return exchange.result


class CallableBackend:
    """Dispatch only enumerated tools to explicitly supplied handlers."""

    def __init__(self, handlers: Mapping[ToolName, Callable[[Mapping[str, Any]], ToolResult]]) -> None:
        self._handlers = dict(handlers)

    def execute(self, request: ToolRequest) -> ToolResult:
        try:
            handler = self._handlers[request.name]
        except KeyError as exc:
            raise LookupError(f"tool is not configured: {request.name.value}") from exc
        result = handler(request.parameters)
        if not isinstance(result, ToolResult):
            raise TypeError("tool handlers must return ToolResult")
        return result


class InvestigationTools:
    """Enforce tool enumeration, budgets, and concise audit references."""

    def __init__(
        self,
        backend: ToolBackend,
        *,
        budget_tracker: BudgetTracker | None = None,
        audit_trail: AuditTrail | None = None,
    ) -> None:
        self.backend = backend
        self.budget_tracker = budget_tracker
        self.audit_trail = audit_trail

    def call(self, name: ToolName | str, parameters: Mapping[str, Any] | None = None) -> ToolResult:
        try:
            tool_name = name if isinstance(name, ToolName) else ToolName(name)
        except ValueError as exc:
            raise ValueError(f"tool is outside the investigation allowlist: {name!r}") from exc
        request = ToolRequest(tool_name, dict(parameters or {}))
        if self.budget_tracker:
            self.budget_tracker.authorize_tool_call(tool_name.value, request.parameters)
            self.budget_tracker.record_tool_call(tool_name.value, request.parameters)
        if self.audit_trail:
            self.audit_trail.append(
                "tool_call",
                {
                    "tool": tool_name.value,
                    "request_hash": request.request_hash,
                    "parameters": redact_sensitive(request.parameters),
                },
            )
        try:
            result = self.backend.execute(request)
        except Exception as exc:
            if self.audit_trail:
                self.audit_trail.append(
                    "tool_error",
                    {
                        "tool": tool_name.value,
                        "request_hash": request.request_hash,
                        "error_type": type(exc).__name__,
                    },
                )
            raise
        if self.audit_trail:
            # Raw evidence belongs in the evidence archive, not duplicated in logs.
            self.audit_trail.append(
                "tool_result",
                {
                    "tool": tool_name.value,
                    "request_hash": request.request_hash,
                    "status": result.status.value,
                    "result_hash": result.result_hash,
                    "error_code": result.error_code,
                },
            )
        return result


# Descriptive compatibility name used by the package's public API.
InvestigationToolRegistry = InvestigationTools


__all__ = [
    "CallableBackend",
    "InvestigationTools",
    "InvestigationToolRegistry",
    "RecordedBackend",
    "RecordedExchange",
    "ToolBackend",
    "ToolName",
    "ToolRequest",
    "ToolResult",
    "ToolStatus",
]
