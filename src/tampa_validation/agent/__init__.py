"""Public API for bounded, auditable agent-assisted evidence retrieval.

Objects in this package produce plans, archived candidate evidence, and pending
deterministic handoffs.  They do not replace deterministic validation or human
review.
"""

from .evidence_store import (
    EvidenceAlreadyArchived,
    EvidenceRecord,
    EvidenceStore,
    EvidenceStoreError,
)
from .investigator import (
    CandidateEvidence,
    EvidenceInvestigator,
    IdentityAssessment,
    IdentityCategory,
    InvestigationRequest,
    InvestigationResult,
    InvestigationSession,
    InvestigationStatus,
    create_deterministic_handoff,
    load_rule_registry,
)
from .planner import BudgetTracker, InvestigationPlan, InvestigationPlanner, StopReason
from .prompts import (
    PromptIntegrityError,
    PromptSpec,
    get_prompt_spec,
    load_agent_config,
    load_prompt,
    prompt_manifest,
    render_prompt,
    runtime_model_metadata,
    verify_prompt_hashes,
)
from .provenance import (
    AuditEvent,
    AuditTrail,
    DeterministicHandoff,
    ModelMetadata,
    PromptProvenance,
)
from .safety import (
    BudgetExceeded,
    BudgetUsage,
    InvestigationBudget,
    assert_safe_agent_output,
    budget_exhausted,
    enforce_budget,
    redact_sensitive,
    wrap_untrusted_evidence,
)
from .sources import SourceDecision, SourceTier, assess_source, is_official_url
from .tools import (
    CallableBackend,
    InvestigationTools,
    RecordedBackend,
    RecordedExchange,
    ToolName,
    ToolRequest,
    ToolResult,
    ToolStatus,
)

# Compatibility name for callers that treat the narrow tool facade as a
# registry.  Both names refer to the same allowlisted implementation.
InvestigationToolRegistry = InvestigationTools

__all__ = [
    "AuditEvent",
    "AuditTrail",
    "BudgetExceeded",
    "BudgetTracker",
    "BudgetUsage",
    "CallableBackend",
    "CandidateEvidence",
    "DeterministicHandoff",
    "EvidenceAlreadyArchived",
    "EvidenceInvestigator",
    "EvidenceRecord",
    "EvidenceStore",
    "EvidenceStoreError",
    "IdentityAssessment",
    "IdentityCategory",
    "InvestigationBudget",
    "InvestigationPlan",
    "InvestigationPlanner",
    "InvestigationRequest",
    "InvestigationResult",
    "InvestigationSession",
    "InvestigationStatus",
    "InvestigationToolRegistry",
    "InvestigationTools",
    "ModelMetadata",
    "PromptIntegrityError",
    "PromptProvenance",
    "PromptSpec",
    "RecordedBackend",
    "RecordedExchange",
    "SourceDecision",
    "SourceTier",
    "StopReason",
    "ToolName",
    "ToolRequest",
    "ToolResult",
    "ToolStatus",
    "assess_source",
    "assert_safe_agent_output",
    "budget_exhausted",
    "create_deterministic_handoff",
    "enforce_budget",
    "get_prompt_spec",
    "is_official_url",
    "load_agent_config",
    "load_prompt",
    "load_rule_registry",
    "prompt_manifest",
    "redact_sensitive",
    "render_prompt",
    "runtime_model_metadata",
    "verify_prompt_hashes",
    "wrap_untrusted_evidence",
]
