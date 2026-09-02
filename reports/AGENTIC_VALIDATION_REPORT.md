# Agentic validation report

## Architecture

This report evaluates a separate evidence-retrieval assistant. Frozen sample -> deterministic baseline -> bounded agent investigation -> archived candidate evidence -> deterministic experimental rule evaluation -> human review. Agent output never writes dataset validation or human-review fields.

## Model

- OpenAI Codex `gpt-5.6-sol`; reasoning `high`; snapshot `unavailable`

Unknown runtime fields are recorded as `unavailable`; requested configuration is not treated as proof of use.

## Prompt provenance

- `prompts/agent/evidence_assessment_v1.md` (v1): `81027cfc6e345f61218d871e4c375300c6170bc0ee00c0e2ad62825688a8b45d`
- `prompts/agent/investigation_v1.md` (v1): `2c99b098a04518195708c1ce22e69a3fb73080722998c94b144f89c847ccd672`
- `prompts/agent/system_v1.md` (v1): `ce14333f117928b1a786dbdc4ffcd902a883eacc9565945a7f1f9d417166629b`

## Evaluation dataset

Benchmark `tdr-agent-evidence-benchmark-v1` contains 18 reproducibly selected cases from the unchanged 150-row frozen core sample. 18 unique cases were investigated: `dev-019`, `dev-024`, `dev-025`, `dev-027`, `dev-046`, `dev-053`, `dev-068`, `dev-072`, `dev-080`, `dev-082`, `dev-083`, `dev-092`, `dev-093`, `hol-001`, `hol-019`, `hol-035`, `hol-039`, `hol-045`. This is an agent-system study, not a replacement sample and not a dataset-accuracy estimate.

## Sources

- `aca-prod.accela.com`: 1
- `arcgis.tampagov.net`: 27
- `www.tampa.gov`: 6

## Results

- Investigations attempted: 22
- Investigations with archived candidate evidence: 22
- Evidence retrieval yield: 100.0%
- Experimental deterministic rule matches: 12
- Unique cases with an experimental rule match: 12
- Release-authorized deterministic resolutions: 0
- Release unresolved cases, before / after: 18 / 18
- Human-review reduction: 0 (experimental rules cannot write release results)
- Ambiguity rate: 18.2%
- Retrieval failure rate: 0.0%
- Conflict discovery rate: 13.6%

These are agent-performance measures, not TDR validity estimates.

## Errors

Statuses: `{"ambiguous_identity": 4, "conflicting_evidence_found": 3, "evidence_found": 15}`. False-association precision remains unmeasured until the blinded human evaluation template is completed. The adversarial suite checks wrong identifiers, near matches, conflicting sources, irrelevant records, missing primary evidence, and prompt injection, but passing fixtures is not a substitute for human precision measurement. No automated agreement is counted as independent review.

## Costs

Model token counts and model cost were not exposed by the agent runtime and remain unavailable. Recorded tool requests: 78; HTTP requests: unavailable. Average duration: unavailable.

## Repeatability

Repeated cases: 2. Same evidence rate: 0.0%; same source rate: 50.0%; same deterministic-classification rate: 50.0%.

## Human audit

The run includes a blinded `agent_evidence_retrieval_evaluation` template. It evaluates relevance, identity, source authority, extraction, overstatement, and ignored contradictions separately from dataset validation. No human agent audit was completed in this run, so evidence precision and false-positive association rate are not yet estimable.

## Protocol deviation

On 2026-09-02, evidence retrieval was prematurely expanded to the remaining 132 frozen-sample cases before the benchmark human audit. Runs D/E/F are excluded exploratory runs. Their outputs were removed from the active experimental workspace before project-owner case-level review and were not used to tune prompts, rules, protocol, or human decisions; the hashes-only audit record is `reproducibility/deviations/2026-09-02-premature-agent-expansion.json`.

## Limitations

Agentic discovery is nondeterministic. Live sources and search indexes change; model backends can change; official portals may be unavailable; absence of evidence is not evidence of absence. "Candidate evidence" means the agent archived an association for evaluation; human review has not established that every association is correct or that every underlying fact was newly discovered. Narrative interpretation remains human-review work. Experimental rule matches have `release_write_enabled=false`. The source attachment for this phase ended mid-bullet at `* Live`; no missing instruction text was reconstructed.

## Scaling recommendation

Do **not** scale to all 150 frozen cases yet. Human-audited evidence precision is unavailable, the rule registry remains experimental, and no agent result is authorized to modify release validation. Complete the blinded agent-evidence audit, review false associations and contradictions, and explicitly approve any release rule before reconsidering scale-up.
