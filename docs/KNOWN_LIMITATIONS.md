# Known limitations

1. The bounded-census claim applies only to features returned by the eight
   named published layers at retrieval. It does not establish that the City
   published every underlying administrative record.
2. The Construction Inspections layer is not the complete Accela permit
   database. Annual counts cannot be interpreted as citywide totals.
3. Issuance and revision statuses do not prove work started or finished.
4. No certificate-of-occupancy or final-inspection bulk table is available in
   the sources accessed by this build.
5. Permit valuation is unavailable. CIP estimated and actual costs are not
   comparable to blank private-development values.
6. Building-footprint year matching is an inference and can be affected by
   assessment lag, additions, reused permits, or imprecise permit points.
7. The public City-only release excludes HCPA parcel-centroid fallback matches.
   City building-footprint matches remain heuristic and are not legal parcel
   joins.
8. A normalized activity can still represent only one permit within a larger
   real-world project. Parent/child clustering awaits complete Accela related-
   record fields.
9. The capital viewer covers active projects for some departments, not the
   complete adopted capital program.
10. Current building footprints cannot by themselves demonstrate change. A
   second historical footprint/aerial vintage is required.
11. Exact addresses are public-source attributes but can still be sensitive;
    aggregate before analyses aimed at individuals or households.
12. Structural validation does not measure real-world accuracy. The included
    150-row stratified sample remains unreviewed until humans complete the
    documented protocol.
13. Cost fields are sparse and concentrated in capital-project sources; they
    cannot support a citywide or neighborhood investment ranking.
14. Exact normalized project names are used to merge matching capital records
    across distinct City layers. Title variants can still remain fragmented,
    while unusually reused exact titles could require manual separation.
15. The Capital Projects Budget Book module is a separately dated snapshot,
    not a complete history of appropriations or budget amendments. Its amount
    fields are reported levels, not proof of expenditures or final costs.
16. Budget Book-to-core capital matching uses exact City project identifiers.
    This avoids name-based false matches but can leave related records
    unmatched when the City changes or omits an identifier.
17. The parcel context module covers only folios exposed through proposed City
    building-footprint matches. It is not a citywide parcel census, and every
    activity-to-parcel link remains pending human review.
18. Parcel values, sale records, years built, and remodel years are contextual
    assessment fields. They do not prove that a development activity started
    or finished and cannot be summed as development investment.
19. The current event table reconstructs only events and observations exposed
    by the archived source fields. Inspection, permit-closure, TCO, CO, and
    final-completion coverage remains unavailable until stronger official
    lifecycle data are obtained.
20. Version 0.9.0 contains one archived core snapshot and therefore no observed
    month-to-month change results yet. The longitudinal contribution begins
    only after a second comparable snapshot is collected.
21. Snapshot differences describe changes in public-layer publication. A new
    row can be an older record newly exposed by a layer, and a disappeared row
    can reflect a filter or service change rather than deletion or cancellation.
22. Native source identifiers are preferred for longitudinal matching. Global
    IDs and OBJECTIDs are fallbacks; a source republish that changes every
    available identifier can appear as paired disappearance/new-record events.
23. A bounded anonymous ACA search flow was verified on August 30, 2026, but it
    is an HTML interface rather than a guaranteed bulk feed. Accela v4 rejected
    Tampa requests without an app ID. ACA results therefore do not establish a
    complete permit, certificate-of-occupancy, or inspection population.
24. Monthly cohorts combine several explicitly labeled date concepts across
    source systems. Application creation, permit record creation, permit
    issuance, actual capital starts, and planned capital starts are not
    interchangeable measures of development activity.
25. Source-date cohorts can reach years before TDR began collecting snapshots.
    They describe dates reported by records that TDR later observed; they do
    not reconstruct when those records entered or left the City's public layer.
26. The canonical source-date table retains forward-looking capital planned
    starts. Researcher-facing extracts isolate those rows under
    `data/planned_events/`; `data/monthly_events/` contains no event date later
    than the snapshot supplying that row. Planned dates remain intentions, not
    observations or proof that work occurred.
