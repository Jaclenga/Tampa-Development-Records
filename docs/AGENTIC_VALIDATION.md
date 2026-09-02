# Agentic evidence validation

The agentic layer is a bounded evidence-retrieval experiment. It does not
validate the dataset, replace the deterministic validators, act as a human
reviewer, or modify any frozen review decision.

## Architecture and authority

```text
frozen benchmark request
  -> constrained evidence investigator
  -> immutable candidate-evidence archive
  -> deterministic identity and claim rules
  -> blinded human evidence audit
```

The investigator may search only the tools and official-source hosts listed in
`config/agentic_validation.json`. It returns plans, action logs, explicit
identity assessments, candidates, conflicts, missing information, usage data,
and a conservative investigation status. It cannot return `verified`, `true`,
or `false`. Retrieved text is untrusted data, including instructions embedded
in descriptions, HTML, PDFs, or metadata.

The deterministic handoff uses the separately versioned experimental registry
in `config/agent_evidence_rules.json`. All rules currently have
`release_write_enabled=false`; every candidate remains queued for human review.
Exact administrative identifiers are required. Address or name similarity is
never sufficient, and identifier collisions remain ambiguous.

## Benchmark

`scripts/build_agent_benchmark.py` reproducibly derives an 18-case benchmark
from the unchanged 150-row core validation sample. It covers conflicts,
repeated identifiers, missing sources, spatial ambiguity, inspection-related
claims, and easier exact-ID cases. Development and holdout partitions are
preserved. This benchmark estimates agent-system behavior only; it is not a
probability sample for dataset accuracy.

Run the deterministic benchmark and recorded-response audit with:

```powershell
$env:PYTHONPATH = 'src'
python scripts/build_agent_benchmark.py --check
python scripts/run_agentic_validation.py --study core --repeat 3 --allow-recorded-live
python -m pytest -q tests/test_agent_safety.py tests/test_agent_core.py tests/test_agent_benchmark.py tests/test_agentic_adversarial.py
```

The runner makes no network or model call. `--allow-recorded-live` authorizes
ingestion of already recorded, allowlisted live-source evidence; it does not
initiate live research. A full-sample run requires separate authorization and
is intentionally not implemented by this benchmark runner.

## Pre-human-audit freeze

The evaluated agent system and Runs A/B/C are frozen in
`reproducibility/agent_benchmark_freeze_v1.json`. This covers the prompts,
configuration, rule registry, agent implementation, benchmark, recorded
responses, evidence archive, and reproduced 18-case result. Verify it before
and after the blinded audit with:

```powershell
python scripts/verify_agent_benchmark_freeze.py
```

Do not edit any frozen artifact during the audit. Store completed human-audit
data as a separate artifact rather than filling the frozen blank template in
place. If prompts, rules, or agent code need improvement, assign a new system
version and run a new benchmark rather than altering this freeze.

Runs D/E/F are excluded exploratory runs, not part of the analyzed experiment.
Their active outputs were removed without project-owner case-level review. The
minimal protocol-deviation record is retained at
`reproducibility/deviations/2026-09-02-premature-agent-expansion.json`.

## Provenance and repeatability

Recorded model identity, reasoning effort, prompt versions and hashes, action
logs, evidence paths, source tiers, retrieval times when exposed, and usage
fields are retained. Unknown runtime data is written as `unavailable`, never
inferred from the requested configuration. Evidence JSON files and underlying
archived-source content are hashed independently.

Repeated investigations measure whether agents discover the same evidence and
whether deterministic re-evaluation reaches the same experimental outcome.
Agreement between agent runs is not independent review. Agent output is
nondeterministic, and live sources, search indexes, and model backends can
change.

## Interpretation

The separate report at `reports/AGENTIC_VALIDATION_REPORT.md` contains agent
evidence yield, ambiguity and conflict rates, repeatability, available cost
information, and the scaling recommendation. These measures must not be mixed
with TDR source-fidelity, transformation-validity, external-outcome, or human
review metrics.

The generated blinded CSV is an evaluation template, not a completed audit.
Until a human fills it, evidence precision and false-positive association rate
remain unknown and no reduction in required human review may be claimed.
