# Data layout

| Directory | Contents | Stability |
| --- | --- | --- |
| `raw/` | Privacy-minimized City source captures | Archived inputs |
| `context/raw/` | Separate parcel and capital-budget context | Archived inputs |
| `processed/` | Analysis-ready tables and manual-review queues | Rebuilt by the release pipeline |
| `integrated/` | Optional GIS + Accela expanded edition | Rebuilt; see its local README |
| `snapshots/` | Compact source observations grouped by date | Immutable once published |
| `monthly_changes/` | Machine-readable differences between snapshots | Derived from snapshots |
| `monthly_events/` | Non-future source-date cohorts | Derived |
| `planned_events/` | Explicit forward-looking source plans | Derived |
| `frozen/` | Signed source freezes used for reproducibility | Immutable |
| `agentic_validation/` | Frozen benchmark cases, responses, and evidence | Immutable benchmark material |
| `coverage/` | Known source gaps and acquisition status | Maintained register |
| `templates/` | Blank official-data request/import templates | Hand maintained |

The primary researcher-facing tables are in `processed/`. Start with
`processed/bounded_census_records.csv` for source records or
`processed/tampa_development_activity.csv` for the consolidated activity view.

The active manual-review indexes are
`processed/manual_validation_core_reliability.csv` (25 independent duplicate
reviews), `processed/manual_validation_accela_audit_plan.csv` (75 targeted
Accela cases), and `processed/manual_validation_longitudinal_initial_plan.csv`
(30 initial change cases). The preserved assignment files named by those
indexes contain the full review fields and remain the authoritative place to
enter judgments.
