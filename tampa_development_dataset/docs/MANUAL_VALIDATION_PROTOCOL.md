# Manual validation protocol

## Status

The review fields in `manual_validation_sample.csv` are blank. The file is a
sampling frame, not a completed accuracy study.

## Sample

The sample contains 150 unique normalized activities. Selection is
deterministic for a given release and preserves the 12 records used in the
earlier public-source pilot.

| Evidence grade | Sample rows |
|---|---:|
| C | 18 |
| D | 54 |
| P | 28 |
| X | 3 |
| U | 47 |
| **Total** | **150** |

Selection also considers source, activity class, neighborhood or council
district, and building-match confidence. The sample is stratified rather than
simple random, so population estimates require grade-specific results or
stratum weights.

## Review procedure

For each row:

1. Open the preserved source record and any official record link.
2. Check the address, parcel or building context, record type, and status.
3. Consult dated supporting evidence when available, such as an inspection,
   certificate of occupancy, project page, announcement, or historical image.
4. Record the evidence URL and a short explanation.
5. Use `unclear` when the sources do not resolve the question.

Permit issuance alone is not evidence of completion.

## Review fields

- `one_activity_one_development`: `yes`, `no`, `unclear`, or
  `not_applicable`.
- `building_match_correct`: `yes`, `no`, `unclear`, or `not_applicable`.
- `likely_realized_classification_correct`: retained for compatibility with
  the earlier pilot. Use `not_applicable` when the legacy prediction is blank.
- `activity_scope`: `new_construction`, `addition`, `alteration`,
  `demolition`, `administrative_or_revision`, `infrastructure`,
  `planning_only`, `other`, or `unclear`.
- `suspected_master_project_id`: reviewer grouping label, when applicable.
- `independent_evidence_url`: supporting source URL.
- `review_notes`: explanation of the judgment and any conflicting evidence.
- `reviewer_id`: stable reviewer name or code.
- `reviewed_at_utc`: ISO 8601 UTC timestamp.

## Independent review

Thirty sampled rows are listed in `manual_validation_second_review.csv`.
Reviewers should complete these rows independently. Report raw agreement and
Cohen's kappa for questions answered by both reviewers, excluding `unclear`
and `not_applicable`. Keep both original reviews when resolving disagreements.

## Reporting

For each metric, report the numerator, denominator, and a 95% confidence
interval:

1. Activity-identity precision.
2. Building-match precision overall and by match method.
3. Activity-class confusion table.
4. Project-fragmentation rate.
5. Agreement between reviewers.

Do not report a single unweighted accuracy rate for the full dataset. Keep the
blank sample under version control and store completed reviews in a separate
versioned file. Exclude personal contact data from review notes.
