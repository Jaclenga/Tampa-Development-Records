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

`development_events.csv` stores permit, status, and progress events. A
`project_closeout` event records an administrative status and is not treated
as a physical completion event.

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
