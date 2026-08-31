"""Configuration and verified endpoint constants for Tampa ACA."""

from __future__ import annotations

from dataclasses import dataclass


COLLECTOR_VERSION = "0.1.0"
BASE_URL = "https://aca-prod.accela.com/TAMPA/"
AGENCY_CODE = "TAMPA"
MODULES = {
    "Building": "Building",
    "Planning": "Planning",
    "RightOfWay": "RightOfWay",
    "Enforcement": "Enforcement",
}


@dataclass(frozen=True)
class CollectorConfig:
    """Network settings chosen to minimize load on the public service."""

    base_url: str = BASE_URL
    agency_code: str = AGENCY_CODE
    user_agent: str = (
        "TampaDevelopmentRecords-AccelaCollector/0.1 "
        "(public-records research; contact: repository maintainer)"
    )
    requests_per_second: float = 1.0
    connect_timeout: float = 10.0
    read_timeout: float = 60.0
    max_retries: int = 4
    backoff_seconds: float = 1.0
    max_pages: int = 500
    max_redirects: int = 5
    max_wire_bytes: int = 25 * 1024 * 1024
    max_decoded_bytes: int = 50 * 1024 * 1024

    def __post_init__(self) -> None:
        if self.requests_per_second <= 0 or self.requests_per_second > 1.0:
            raise ValueError("requests_per_second must be greater than 0 and no more than 1.0")
        if self.connect_timeout <= 0 or self.read_timeout <= 0:
            raise ValueError("timeouts must be positive")
        if self.max_retries < 0 or self.max_pages < 1:
            raise ValueError("max_retries and max_pages must be non-negative/positive")
        if self.max_redirects < 0:
            raise ValueError("max_redirects must be non-negative")
        if self.max_wire_bytes < 1 or self.max_decoded_bytes < 1:
            raise ValueError("response byte limits must be positive")
        if self.max_wire_bytes > self.max_decoded_bytes:
            raise ValueError("max_wire_bytes cannot exceed max_decoded_bytes")


def module_url(module: str, base_url: str = BASE_URL) -> str:
    if module not in MODULES:
        raise ValueError(f"Unsupported module {module!r}; choose from {sorted(MODULES)}")
    name = MODULES[module]
    return f"{base_url.rstrip('/')}/Cap/CapHome.aspx?module={name}&TabName={name}"
