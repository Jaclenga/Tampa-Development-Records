"""Hashing and audit primitives for agent-assisted evidence investigations.

The objects in this module deliberately record observable actions and concise
outputs.  They are not a place to persist model chain-of-thought.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping, Sequence


GENESIS_HASH = "0" * 64
_FORBIDDEN_REASONING_KEYS = {
    "chain_of_thought",
    "chain-of-thought",
    "hidden_reasoning",
    "private_reasoning",
    "internal_reasoning",
    "scratchpad",
}
_SECRET_KEY_RE = re.compile(
    r"(?:^|_)(?:api_?key|authorization|cookie|password|secret|session|access_?token|refresh_?token)(?:$|_)",
    re.IGNORECASE,
)
_BEARER_VALUE_RE = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+")
_QUERY_SECRET_RE = re.compile(
    r"(?i)([?&](?:api_?key|access_?token|token|password|secret)=)[^&#\s]+"
)


def utc_now() -> str:
    """Return an explicit, second-resolution UTC timestamp."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _json_value(value: Any) -> Any:
    if is_dataclass(value):
        return _json_value(asdict(value))
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(f"value of type {type(value).__name__} is not JSON serializable")


def canonical_json(value: Any) -> str:
    """Serialize a value in the stable form used for all provenance hashes."""
    return json.dumps(
        _json_value(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def sha256_payload(value: Any) -> str:
    return sha256_bytes(canonical_json(value).encode("utf-8"))


def sanitize_audit_payload(value: Any) -> Any:
    """Remove secrets and reject fields intended to contain hidden reasoning.

    Secret-shaped keys are retained with a redaction marker so the audit trail
    still shows that a field was supplied.  Hidden-reasoning fields are rejected
    outright; accepting and redacting them would encourage callers to collect
    data that should never be requested.
    """
    if is_dataclass(value):
        return sanitize_audit_payload(asdict(value))
    if isinstance(value, Mapping):
        cleaned: dict[str, Any] = {}
        for raw_key, item in value.items():
            key = str(raw_key)
            if key.lower() in _FORBIDDEN_REASONING_KEYS:
                raise ValueError(f"audit payload must not contain {key!r}")
            if _SECRET_KEY_RE.search(key):
                cleaned[key] = "[REDACTED]"
            else:
                cleaned[key] = sanitize_audit_payload(item)
        return cleaned
    if isinstance(value, (list, tuple)):
        return [sanitize_audit_payload(item) for item in value]
    if isinstance(value, str):
        redacted = _BEARER_VALUE_RE.sub("Bearer [REDACTED]", value)
        return _QUERY_SECRET_RE.sub(r"\1[REDACTED]", redacted)
    return _json_value(value)


@dataclass(frozen=True)
class ModelMetadata:
    """Runtime-reported model configuration; unknown values stay unavailable."""

    provider: str = "unavailable"
    product_api: str = "unavailable"
    model_identifier: str = "unavailable"
    reasoning_effort: str = "unavailable"
    model_snapshot_version: str = "unavailable"
    temperature: str | float = "unavailable"
    seed: str | int = "unavailable"
    generation_parameters: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_runtime(cls, metadata: Mapping[str, Any] | None) -> "ModelMetadata":
        supplied = dict(metadata or {})
        if "product_api" not in supplied and "product" in supplied:
            supplied["product_api"] = supplied.pop("product")
        if "model_snapshot_version" not in supplied and "model_snapshot" in supplied:
            supplied["model_snapshot_version"] = supplied.pop("model_snapshot")
        known = {
            "provider",
            "product_api",
            "model_identifier",
            "reasoning_effort",
            "model_snapshot_version",
            "temperature",
            "seed",
        }
        values = {key: supplied.get(key, "unavailable") for key in known}
        values["generation_parameters"] = {
            key: value for key, value in supplied.items() if key not in known
        }
        return cls(**values)


@dataclass(frozen=True)
class PromptProvenance:
    version: str
    sha256: str

    def __post_init__(self) -> None:
        if not self.version.strip():
            raise ValueError("prompt version is required")
        if not re.fullmatch(r"[0-9a-f]{64}", self.sha256):
            raise ValueError("prompt sha256 must be a lowercase SHA-256 digest")


@dataclass(frozen=True)
class AuditEvent:
    sequence: int
    event_type: str
    occurred_at_utc: str
    payload: Mapping[str, Any]
    previous_hash: str
    event_hash: str

    def as_dict(self) -> dict[str, Any]:
        return _json_value(asdict(self))


class AuditTrail:
    """In-memory, append-only hash chain of externally useful audit events."""

    def __init__(self, events: Sequence[AuditEvent] = ()) -> None:
        self._events: list[AuditEvent] = list(events)
        if not self.verify():
            raise ValueError("invalid audit event hash chain")

    @property
    def events(self) -> tuple[AuditEvent, ...]:
        return tuple(self._events)

    def append(
        self,
        event_type: str,
        payload: Mapping[str, Any],
        *,
        occurred_at_utc: str | None = None,
    ) -> AuditEvent:
        if not event_type.strip():
            raise ValueError("audit event type is required")
        clean = sanitize_audit_payload(payload)
        sequence = len(self._events) + 1
        previous = self._events[-1].event_hash if self._events else GENESIS_HASH
        body = {
            "sequence": sequence,
            "event_type": event_type,
            "occurred_at_utc": occurred_at_utc or utc_now(),
            "payload": clean,
            "previous_hash": previous,
        }
        event = AuditEvent(event_hash=sha256_payload(body), **body)
        self._events.append(event)
        return event

    def verify(self) -> bool:
        previous = GENESIS_HASH
        for expected_sequence, event in enumerate(self._events, start=1):
            if event.sequence != expected_sequence or event.previous_hash != previous:
                return False
            body = event.as_dict()
            claimed_hash = body.pop("event_hash")
            if sha256_payload(body) != claimed_hash:
                return False
            previous = event.event_hash
        return True

    def write_jsonl(self, path: Path) -> None:
        """Create a new audit file; an existing log is never overwritten."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x", encoding="utf-8", newline="\n") as stream:
            for event in self._events:
                stream.write(canonical_json(event.as_dict()) + "\n")


@dataclass(frozen=True)
class DeterministicHandoff:
    """A candidate-only envelope; it contains no agent-authored outcome."""

    investigation_id: str
    sample_id: str
    claim: str
    evidence_ids: tuple[str, ...]
    discovered_by: str
    evaluated_by: str
    rule_id: str
    evaluation_status: str = "pending_deterministic_evaluation"

    def __post_init__(self) -> None:
        if self.discovered_by != "agent":
            raise ValueError("agent evidence handoffs must identify discovered_by=agent")
        if self.evaluated_by != "deterministic_rule":
            raise ValueError("agent evidence may only be evaluated by a deterministic rule")
        if self.evaluation_status != "pending_deterministic_evaluation":
            raise ValueError("a handoff cannot contain an already-applied conclusion")
        if not self.evidence_ids:
            raise ValueError("a handoff requires candidate evidence")
