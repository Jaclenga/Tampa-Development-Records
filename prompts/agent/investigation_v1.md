# Investigation task v1

Create a short, externally useful investigation plan and investigate only the
unresolved claims in the request below. Do not expose private reasoning.

## Structured request

{{INVESTIGATION_REQUEST_JSON}}

## Enforced budget

{{BUDGET_JSON}}

## Enforced source policy

{{SOURCE_POLICY_JSON}}

Use the narrow tools exposed by the application. For each unresolved claim:

1. name the authoritative source most likely to contain the needed evidence;
2. state a concise strategy as an array of observable actions;
3. retrieve within budget and preserve the query/result provenance;
4. compare exact administrative identifiers first;
5. report exact identifiers, supporting fields, conflicting fields, and the
   number of plausible candidates;
6. submit candidate evidence for archiving and deterministic re-evaluation.

Use only these identity categories: `exact_identifier`,
`strong_multi_field`, `ambiguous`, `conflicting`, or `rejected`. Do not invent a
numeric confidence score. Unless an approved deterministic identity rule
accepts the association, set `accepted_for_rule_evaluation` to `false`.

If evidence is narrative, equivocal, secondary-only, or cannot be reduced to
an approved deterministic rule, set `requires_human_review` to `true`. The
output is a candidate-evidence report, not a validation decision.

Return structured JSON only. Include `investigation_id`, `sample_id`, `claim`,
`status`, `plan`, `candidate_evidence`, `identity_assessment`, `conflicts`,
`missing_information`, `recommended_next_action`,
`requires_human_review`, `prompt_version`, and `prompt_hash`.
