"""Respectful collector for Tampa's public Accela Citizen Access portal."""

from .client import AccelaClient, AccessRestricted, CollectionError
from .config import COLLECTOR_VERSION, MODULES, CollectorConfig
from .models import CollectionResult, Inspection, NormalizedRecord, SearchQuery

__all__ = [
    "AccelaClient",
    "AccessRestricted",
    "CollectionError",
    "CollectionResult",
    "CollectorConfig",
    "Inspection",
    "NormalizedRecord",
    "SearchQuery",
    "COLLECTOR_VERSION",
    "MODULES",
]

__version__ = COLLECTOR_VERSION
