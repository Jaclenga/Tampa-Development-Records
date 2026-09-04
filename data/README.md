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
