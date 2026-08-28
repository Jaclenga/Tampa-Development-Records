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
