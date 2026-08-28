# Evidence fields

The source census records what the City published. Separate tables describe
what the available records indicate about construction, completion, project
relationships, and reported costs.

## Status values

The following fields use `yes`, `no`, `unknown`, or `not_applicable`:

- `physical_work_started`
- `physical_work_completed`
- `certificate_of_occupancy_issued`
- `final_inspection_passed`
- `project_cancelled`

`unknown` means the available source does not answer the question. Planning
cases use `not_applicable` for construction and occupancy fields.

Permit issuance, a current building footprint, an assessment year, or a
capital-project closeout status does not by itself establish completion.

## Evidence grades

| Grade | Evidence |
|---|---|
| A1 | Certificate of occupancy issued |
| A2 | Final inspection passed |
| A3 | Official notice of substantial or final completion |
| B1 | Dated before-and-after imagery showing construction |
| B2 | Multiple independent dated sources showing completion |
| C | Official construction-in-progress inspection or announcement |
| D | Permit issued or funding approved |
| P | Planning or application record |
| X | Cancelled, denied, withdrawn, or expired record |
| U | Insufficient evidence |

The archived GIS layers support grades C, D, P, X, and U. They do not include
the bulk inspection and certificate records needed to assign A1 or A2. A
compatible building year is stored as supporting information but does not
raise a record to grade B.

## Project links

`master_projects.csv` starts with one provisional project per normalized
activity. `master_project_candidates.csv` lists pairs that share a normalized
address or City building folio. Candidate pairs remain separate until they are
reviewed; a shared address alone is not sufficient to merge them.

`development_events.csv` stores long-format source observations and explicitly
dated lifecycle events. Every source feature contributes one
`source_record_observed` row. Additional rows are created only when a source
exposes an applicable filing, hearing, issuance, planned-date, reported actual-
date, phase, or status field.

Each event retains `activity_id`, `master_project_id`, source-record lineage,
raw source status, normalized stage, evidence URL, source name, observation
time, evidence strength, source field, and an `is_inferred` flag. Historical
event identifiers do not depend on observation time; snapshot-observation event
identifiers do, so later monthly observations can coexist.

`construction_started_reported` is an explicit phase/status interpretation and
is marked inferred when an exact start date is unavailable.
`project_closeout_reported` records an administrative label. Neither is treated
as physical completion. Final-inspection, TCO, CO, and construction-completion
event types are reserved for stronger official lifecycle sources and are not
created from the current GIS layers.

## Pending validation

`manual_validation_sample.csv` contains a seeded, stratified 150-record study:
100 development/debugging rows and a separately randomized 50-row final
holdout. Permit, planning, historic-preservation, capital-project, and
cross-source-merge strata have frozen quotas and explicit selection weights.
`manual_validation_second_review.csv` assigns 50 rows for blinded independent
review. Accuracy, agreement, and match-precision statistics remain pending
until humans complete the cited-evidence reviews under protocol 1.0.0.

`scripts/calculate_recall.py` compares the dataset with a sampled official permit
list. It reports results by permit category and period rather than combining
unlike permit types into one rate.

## Reported amounts

`investment_amounts.csv` stores each nonzero source amount with its stated
type, sector, price year, estimate flag, and final flag. Permit valuation,
capital estimates, contract awards, expenditures, assessment changes, and
modeled construction costs are separate measures.

`public_finance_events.csv` extends that separation for the Budget Book context
module. It stores reported estimate levels, reported actual-cost levels, and
funded-status observations as distinct event types. It does not infer
appropriations, amendments, transfers, payments, or final cost.
