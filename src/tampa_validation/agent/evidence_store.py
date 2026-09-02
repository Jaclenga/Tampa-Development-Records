"""Append-only storage for evidence bytes and their source provenance."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
import re
from typing import Any, Mapping

from .provenance import GENESIS_HASH, canonical_json, sha256_bytes, sha256_payload, utc_now


_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_PROHIBITED_PARAMETER_KEYS = re.compile(
    r"(?:api_?key|authorization|cookie|password|secret|session|access_?token|refresh_?token)",
    re.IGNORECASE,
)


class EvidenceStoreError(RuntimeError):
    pass


class EvidenceAlreadyArchived(EvidenceStoreError):
    pass


def _validate_identifier(label: str, value: str) -> str:
    if not _SAFE_IDENTIFIER.fullmatch(value):
        raise ValueError(f"{label} must be a simple non-empty identifier")
    return value


def _safe_parameters(parameters: Mapping[str, Any]) -> dict[str, Any]:
    def check(value: Any) -> None:
        if isinstance(value, Mapping):
            for key, item in value.items():
                if _PROHIBITED_PARAMETER_KEYS.search(str(key)):
                    raise ValueError(
                        f"request parameter {key!r} may contain a secret and cannot be archived"
                    )
                check(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                check(item)

    check(parameters)
    # Canonical round trip both validates JSON compatibility and detaches caller-owned objects.
    return json.loads(canonical_json(parameters))


@dataclass(frozen=True)
class EvidenceRecord:
    evidence_id: str
    sequence: int
    investigation_id: str
    sample_id: str
    source: str
    url_or_endpoint: str
    retrieved_at_utc: str
    administrative_record_id: str
    request_parameters: Mapping[str, Any]
    evidence_type: str
    archived_path: str
    content_sha256: str
    mime_type: str
    source_state: str
    evidence_class: str
    previous_record_hash: str
    record_hash: str
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return json.loads(canonical_json(asdict(self)))

    @classmethod
    def from_dict(cls, values: Mapping[str, Any]) -> "EvidenceRecord":
        return cls(**dict(values))


class EvidenceStore:
    """Store each retrieval observation once without mutating prior observations."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _directory(self, investigation_id: str) -> Path:
        _validate_identifier("investigation_id", investigation_id)
        directory = (self.root / investigation_id).resolve()
        if self.root not in directory.parents:
            raise ValueError("investigation archive path escapes the evidence root")
        return directory

    def records(self, investigation_id: str) -> tuple[EvidenceRecord, ...]:
        directory = self._directory(investigation_id)
        if not directory.exists():
            return ()
        records: list[EvidenceRecord] = []
        for path in sorted(directory.glob("*.metadata.json")):
            records.append(EvidenceRecord.from_dict(json.loads(path.read_text(encoding="utf-8"))))
        return tuple(records)

    def archive(
        self,
        *,
        investigation_id: str,
        sample_id: str,
        source: str,
        content: bytes,
        url_or_endpoint: str = "",
        retrieved_at_utc: str | None = None,
        administrative_record_id: str = "",
        request_parameters: Mapping[str, Any] | None = None,
        evidence_type: str,
        mime_type: str,
        source_state: str,
        evidence_class: str,
        metadata: Mapping[str, Any] | None = None,
    ) -> EvidenceRecord:
        _validate_identifier("sample_id", sample_id)
        if not source.strip() or not evidence_type.strip() or not mime_type.strip():
            raise ValueError("source, evidence_type, and mime_type are required")
        if source_state not in {"live", "archived"}:
            raise ValueError("source_state must be live or archived")
        if evidence_class not in {"primary", "secondary", "discovery_only"}:
            raise ValueError("invalid evidence_class")
        if not isinstance(content, bytes):
            raise TypeError("evidence content must be bytes")

        directory = self._directory(investigation_id)
        directory.mkdir(parents=True, exist_ok=True)
        existing = self.records(investigation_id)
        if existing and not self.verify(investigation_id):
            raise EvidenceStoreError("existing evidence chain failed verification; refusing append")
        sequence = len(existing) + 1
        previous_hash = existing[-1].record_hash if existing else GENESIS_HASH
        content_hash = sha256_bytes(content)
        retrieval_time = retrieved_at_utc or utc_now()
        safe_parameters = _safe_parameters(request_parameters or {})
        safe_metadata = _safe_parameters(metadata or {})
        observation = {
            "sequence": sequence,
            "investigation_id": investigation_id,
            "sample_id": sample_id,
            "source": source,
            "url_or_endpoint": url_or_endpoint,
            "retrieved_at_utc": retrieval_time,
            "administrative_record_id": administrative_record_id,
            "request_parameters": safe_parameters,
            "evidence_type": evidence_type,
            "content_sha256": content_hash,
            "mime_type": mime_type,
            "source_state": source_state,
            "evidence_class": evidence_class,
            "previous_record_hash": previous_hash,
            "metadata": safe_metadata,
        }
        evidence_id = sha256_payload(observation)
        stem = f"{sequence:06d}_{evidence_id}"
        content_path = directory / f"{stem}.evidence"
        archived_path = content_path.relative_to(self.root).as_posix()
        record_body = {**observation, "evidence_id": evidence_id, "archived_path": archived_path}
        record_hash = sha256_payload(record_body)
        record = EvidenceRecord(record_hash=record_hash, **record_body)
        metadata_path = directory / f"{stem}.metadata.json"

        try:
            with content_path.open("xb") as stream:
                stream.write(content)
            with metadata_path.open("x", encoding="utf-8", newline="\n") as stream:
                stream.write(canonical_json(record.as_dict()) + "\n")
        except FileExistsError as exc:
            raise EvidenceAlreadyArchived(f"evidence observation already exists: {evidence_id}") from exc
        return record

    def verify(self, investigation_id: str) -> bool:
        try:
            previous = GENESIS_HASH
            for expected_sequence, record in enumerate(self.records(investigation_id), start=1):
                if record.sequence != expected_sequence or record.previous_record_hash != previous:
                    return False
                content_path = (self.root / record.archived_path).resolve()
                if self.root not in content_path.parents or not content_path.is_file():
                    return False
                if sha256_bytes(content_path.read_bytes()) != record.content_sha256:
                    return False
                body = record.as_dict()
                claimed_hash = body.pop("record_hash")
                if sha256_payload(body) != claimed_hash:
                    return False
                previous = record.record_hash
            return True
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            return False
