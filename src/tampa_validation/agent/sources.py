"""Allowlisted source hierarchy for agentic evidence retrieval."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlsplit


class SourceTier(str, Enum):
    """Research authority tiers, ordered by meaning rather than Enum value."""

    ARCHIVED_PRIMARY = "tier_1_archived_primary"
    LIVE_PRIMARY = "tier_2_live_primary"
    SECONDARY = "tier_3_secondary"
    DISCOVERY_ONLY = "tier_4_discovery_only"


@dataclass(frozen=True)
class SourceDecision:
    """Deterministic source-policy result."""

    allowed: bool
    tier: SourceTier | None
    reason: str
    normalized_host: str | None
    may_support_claim: bool
    purpose: str


class SourcePolicyError(ValueError):
    """Raised when source policy configuration is malformed."""


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _load_default_policy() -> Mapping[str, Any]:
    path = _repository_root() / "config" / "agentic_validation.json"
    with path.open("r", encoding="utf-8") as handle:
        config = json.load(handle)
    return config["source_policy"]


def _policy(mapping: Mapping[str, Any] | None) -> Mapping[str, Any]:
    if mapping is None:
        return _load_default_policy()
    if "source_policy" in mapping:
        nested = mapping["source_policy"]
        if not isinstance(nested, Mapping):
            raise SourcePolicyError("source_policy must be an object")
        return nested
    return mapping


def normalize_host(host: str) -> str:
    """Normalize a DNS hostname for exact/suffix allowlist comparison."""

    cleaned = host.strip().lower().rstrip(".")
    if not cleaned or any(char.isspace() for char in cleaned):
        raise SourcePolicyError("invalid empty or whitespace-containing hostname")
    try:
        return cleaned.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise SourcePolicyError("hostname cannot be IDNA-normalized") from exc


def host_matches_allowlist(host: str, allowed_hosts: list[str] | tuple[str, ...]) -> bool:
    """Match a host exactly or as a subdomain, never by string suffix alone."""

    normalized = normalize_host(host)
    for entry in allowed_hosts:
        allowed = normalize_host(str(entry).lstrip("."))
        if normalized == allowed or normalized.endswith("." + allowed):
            return True
    return False


def _parse_https_url(url: str, policy: Mapping[str, Any]) -> tuple[str | None, str | None]:
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError:
        return None, "malformed_url"
    schemes = tuple(str(item).lower() for item in policy.get("allowed_schemes", ["https"]))
    if parsed.scheme.lower() not in schemes:
        return None, "scheme_not_allowed"
    if not parsed.hostname:
        return None, "hostname_missing"
    if parsed.username is not None or parsed.password is not None:
        return None, "userinfo_not_allowed"
    if port is not None and port not in tuple(policy.get("allowed_ports", [443])):
        return None, "port_not_allowed"
    try:
        return normalize_host(parsed.hostname), None
    except SourcePolicyError:
        return None, "hostname_invalid"


def assess_source(
    url: str | None,
    *,
    archived: bool = False,
    purpose: str = "evidence",
    policy: Mapping[str, Any] | None = None,
) -> SourceDecision:
    """Classify a proposed retrieval target under the configured allowlist.

    Unknown hosts are denied.  A discovery-only source can be queried only when
    explicitly allowlisted and can never support a validation claim by itself.
    An archived record is Tier 1 only when the caller is inspecting already
    archived content; this function grants no filesystem write authority.
    """

    if purpose not in {"evidence", "discovery"}:
        raise ValueError("purpose must be 'evidence' or 'discovery'")
    selected = _policy(policy)

    if not url and not archived:
        return SourceDecision(False, None, "url_required", None, False, purpose)

    primary_hosts = list(selected.get("live_primary_hosts", []))
    exact_primary_hosts = {
        normalize_host(str(item))
        for item in selected.get("live_primary_exact_hosts", [])
    }

    host: str | None = None
    if url:
        host, error = _parse_https_url(url, selected)
        if error:
            return SourceDecision(False, None, error, host, False, purpose)
        assert host is not None

    is_primary_host = host is not None and (
        host in exact_primary_hosts or host_matches_allowlist(host, primary_hosts)
    )
    if archived:
        if host is not None and not is_primary_host:
            return SourceDecision(
                False,
                None,
                "archived_source_not_allowlisted_as_primary",
                host,
                False,
                purpose,
            )
        return SourceDecision(
            allowed=True,
            tier=SourceTier.ARCHIVED_PRIMARY,
            reason="already_archived_primary_evidence",
            normalized_host=host,
            may_support_claim=True,
            purpose=purpose,
        )

    assert host is not None
    if is_primary_host:
        return SourceDecision(
            True,
            SourceTier.LIVE_PRIMARY,
            "allowlisted_live_primary",
            host,
            True,
            purpose,
        )

    secondary_hosts = list(selected.get("secondary_hosts", []))
    if host_matches_allowlist(host, secondary_hosts):
        if not selected.get("secondary_sources_enabled", False):
            return SourceDecision(
                False,
                SourceTier.SECONDARY,
                "secondary_sources_disabled",
                host,
                False,
                purpose,
            )
        return SourceDecision(
            True,
            SourceTier.SECONDARY,
            "allowlisted_secondary",
            host,
            False,
            purpose,
        )

    discovery_hosts = list(selected.get("discovery_hosts", []))
    if host_matches_allowlist(host, discovery_hosts):
        allowed = purpose == "discovery"
        return SourceDecision(
            allowed,
            SourceTier.DISCOVERY_ONLY,
            "allowlisted_discovery_only" if allowed else "discovery_source_not_evidence",
            host,
            False,
            purpose,
        )

    return SourceDecision(False, None, "host_not_allowlisted", host, False, purpose)


def is_official_url(url: str, policy: Mapping[str, Any] | None = None) -> bool:
    """Return whether *url* is an allowlisted live primary source."""

    decision = assess_source(url, policy=policy)
    return decision.allowed and decision.tier is SourceTier.LIVE_PRIMARY


def source_tier_rank(tier: SourceTier) -> int:
    """Return the documented preference rank (lower is more authoritative)."""

    return {
        SourceTier.ARCHIVED_PRIMARY: 1,
        SourceTier.LIVE_PRIMARY: 2,
        SourceTier.SECONDARY: 3,
        SourceTier.DISCOVERY_ONLY: 4,
    }[tier]


__all__ = [
    "SourceDecision",
    "SourcePolicyError",
    "SourceTier",
    "assess_source",
    "host_matches_allowlist",
    "is_official_url",
    "normalize_host",
    "source_tier_rank",
]
